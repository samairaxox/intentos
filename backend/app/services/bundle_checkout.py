from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.entities import Cart, Order, OrderItem, AuditEvent
from app.services import plans


def verify_bundle(db, order):
    initial=db.get(Cart,order.cart_id)
    if not initial: raise HTTPException(409,"Cart no longer exists")
    plan=plans.get_plan(db,initial.plan_id)
    cart=plans.get_cart(db,order.cart_id)
    plans.ensure_current(db,plan,cart.snapshot)
    if cart.status!="ORDERED" or cart.snapshot["total_cost"]!=order.amount:
        raise HTTPException(409,"Order snapshot mismatch")


def create_bundle_order(db, request):
    previous=db.scalar(select(Order).where(Order.idempotency_key==request.idempotency_key))
    if previous:
        if previous.cart_id!=request.cart_id:
            raise HTTPException(409,"Idempotency key reused for another cart")
        cart=db.get(Cart,previous.cart_id)
        if cart.version!=request.cart_version: raise HTTPException(409,"Cart version conflict")
        return previous
    initial=db.get(Cart,request.cart_id)
    if not initial: raise HTTPException(404,"Cart not found")
    plan=plans.get_plan(db,initial.plan_id)
    cart=plans.get_cart(db,request.cart_id)
    if cart.status!="ACTIVE" or cart.version!=request.cart_version:
        raise HTTPException(409,"Cart is stale, ordered or changed; review it again")
    plans.ensure_current(db,plan,cart.snapshot)
    amount=sum(line["product"]["price"]*line["quantity"] for line in cart.snapshot["items"])
    if amount!=cart.snapshot["total_cost"] or amount>plan.intent["total_budget"]:
        raise HTTPException(409,"Invalid cart totals")
    order=Order(session_id=plan.session_id,product_id=None,cart_id=cart.id,amount=amount,currency=plan.intent["currency"],idempotency_key=request.idempotency_key)
    try:
        db.add(order);db.flush()
        for line in cart.snapshot["items"]:
            product=line["product"]
            db.add(OrderItem(order_id=order.id,product_id=product["id"],quantity=line["quantity"],unit_price=product["price"],seller=product["seller"],snapshot=product))
        db.add(AuditEvent(order_id=order.id,event="PENDING_APPROVAL"))
        cart.status="ORDERED"
        db.commit()
        return order
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(Order).where(Order.idempotency_key==request.idempotency_key))
        if existing and existing.cart_id==request.cart_id: return existing
        raise HTTPException(409,"Cart already has an order or idempotency key is in use")
