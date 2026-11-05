from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.models.entities import Order, Payment, AuditEvent, PurchaseSession, Product
from app.models.schemas import Intent
from app.services.optimization import eligible
from app.core.config import settings
from app.services.payments import MockPaymentGateway

def get_order(db, order_id):
    order = db.get(Order, order_id)
    if not order: raise HTTPException(404, "Order not found")
    return order

def event(db, order, name):
    db.add(AuditEvent(order_id=order.id, event=name))

def verify(db, order):
    product = db.scalar(select(Product).where(Product.id==order.product_id).with_for_update().execution_options(populate_existing=True))
    session = db.get(PurchaseSession, order.session_id)
    if not product or not session or not eligible(product.data, Intent.model_validate(session.result["intent"])):
        raise HTTPException(409, "Product is unavailable or no longer meets constraints")
    if product.data["price"] != order.amount:
        raise HTTPException(409, "Price changed. Create a new order and approve the new amount.")

def create_order(db, request):
    existing = db.scalar(select(Order).where(Order.idempotency_key == request.idempotency_key))
    if existing:
        if existing.session_id != request.session_id or existing.product_id != request.product_id:
            raise HTTPException(409, "Idempotency key reused for a different order")
        return existing
    session = db.get(PurchaseSession, request.session_id)
    if not session: raise HTTPException(404, "Purchase session not found")
    if request.product_id not in [r["product"]["id"] for r in session.result.get("recommendations",[])]:
        raise HTTPException(422, "Select an eligible recommendation from this session")
    product = db.get(Product, request.product_id)
    if not product: raise HTTPException(404, "Product not found")
    order = Order(session_id=session.id, product_id=product.id, amount=product.data["price"], idempotency_key=request.idempotency_key)
    verify(db, order)
    try:
        db.add(order); db.flush()
        event(db, order, "PENDING_APPROVAL")
        db.commit()
    except IntegrityError:
        db.rollback()
        return create_order(db,request)
    return order

def approve(db, order_id):
    order = get_order(db,order_id)
    if order.status == "APPROVED": return order
    verify(db,order)
    changed = db.execute(update(Order).where(Order.id==order_id, Order.status=="PENDING_APPROVAL").values(status="APPROVED"))
    if changed.rowcount != 1:
        db.rollback(); raise HTTPException(409,"Order cannot be approved in its current state")
    event(db,order,"APPROVED"); db.commit(); db.refresh(order)
    return order

def cancel(db, order_id):
    order = get_order(db,order_id)
    changed = db.execute(update(Order).where(Order.id==order_id, Order.status.in_(["PENDING_APPROVAL","APPROVED"])).values(status="CANCELLED"))
    if changed.rowcount != 1:
        db.rollback(); raise HTTPException(409,"Order cannot be cancelled in its current state")
    event(db,order,"CANCELLED"); db.commit(); db.refresh(order)
    return order

def pay(db, order_id, request):
    if settings.payment_mode != "mock": raise HTTPException(503,"Only mock payments are supported")
    order = get_order(db,order_id)
    previous = db.scalar(select(Payment).where(Payment.order_id==order_id))
    if previous:
        if previous.idempotency_key != request.idempotency_key:
            raise HTTPException(409,"Order already has a payment attempt")
        if (previous.status == "PAYMENT_FAILED") != request.simulate_failure:
            raise HTTPException(409,"Idempotency key reused with different parameters")
        return previous
    verify(db,order)
    changed = db.execute(update(Order).where(Order.id==order_id, Order.status=="APPROVED").values(status="PAYMENT_PROCESSING"))
    if changed.rowcount != 1:
        db.rollback(); raise HTTPException(409,"Explicit approval is required; order cannot be paid in its current state")
    try:
        event(db,order,"PAYMENT_PROCESSING")
        status = MockPaymentGateway().charge(order_id=order.id, amount=order.amount, simulate_failure=request.simulate_failure).status
        payment = Payment(order_id=order.id,idempotency_key=request.idempotency_key,status=status,amount=order.amount)
        db.add(payment)
        order.status = status
        event(db,order,status)
        db.commit(); db.refresh(payment)
        return payment
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,"Payment already exists or idempotency key is in use")
