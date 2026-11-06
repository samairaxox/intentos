import logging
from app.core.time import utc_iso
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import PurchaseSession, Product, AuditEvent, Payment, OrderItem
from app.models.schemas import AnalyzeRequest, CreateOrder, Approval, PayRequest, OrderOut, PaymentOut, CatalogProduct, PurchaseOut, EventOut
from app.services.catalog import LocalCatalogProvider
from app.agents.checkpoints import PlanningInterrupted
from app.services.gemini import GeminiService, AIUnavailable
from app.agents.workflow import build_workflow
from app.services import orders

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)

def get_ai(): return GeminiService()

@router.get("/products", response_model=list[CatalogProduct])
def products(db: Session = Depends(get_db)) -> list[dict]:
    return LocalCatalogProvider(db).discover(["laptop"])

@router.post("/purchases/analyze", status_code=201, response_model=PurchaseOut)
def analyze(request: AnalyzeRequest, db: Session = Depends(get_db), ai = Depends(get_ai)) -> dict:
    from app.services import single_recovery
    try:session=single_recovery.create(db,request.text,ai)
    except (AIUnavailable,PlanningInterrupted) as exc:
        raise HTTPException(503,{'message':str(exc),'session_id':getattr(exc,'purchase_session_id',None)}) from exc
    return single_recovery.present(session)

@router.post('/purchases/{session_id}/resume',response_model=PurchaseOut)
def resume_single(session_id:str,db:Session=Depends(get_db),ai=Depends(get_ai)):
    from app.services import single_recovery
    try:session=single_recovery.run(db,orders.single_session(db,session_id),ai,resume=True)
    except (AIUnavailable,PlanningInterrupted) as exc:
        raise HTTPException(503,{'message':str(exc),'session_id':session_id}) from exc
    return single_recovery.present(session)

@router.get("/purchases/{session_id}", response_model=PurchaseOut)
def purchase(session_id: str, db: Session = Depends(get_db)) -> dict:
    session = orders.single_session(db,session_id)
    from app.services.single_recovery import present
    return present(session)

@router.post("/orders", response_model=OrderOut, status_code=201)
def create(request: CreateOrder, db: Session = Depends(get_db)):
    return orders.create_order(db,request)

@router.get("/orders/{order_id}", response_model=OrderOut)
def read_order(order_id: str, db: Session = Depends(get_db)):
    order = orders.get_order(db,order_id)
    payment = db.scalar(select(Payment).where(Payment.order_id==order_id))
    items=list(db.scalars(select(OrderItem).where(OrderItem.order_id==order_id)))
    return {**OrderOut.model_validate(order).model_dump(), "payment":PaymentOut.model_validate(payment) if payment else None,
            "items":[{"product_id":i.product_id,"quantity":i.quantity,"unit_price":i.unit_price,"seller":i.seller,"snapshot":i.snapshot} for i in items]}

@router.post("/orders/{order_id}/approve", response_model=OrderOut)
def approve(order_id: str, request: Approval, db: Session = Depends(get_db)):
    return orders.approve(db,order_id)

@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
def cancel(order_id: str, db: Session = Depends(get_db)):
    return orders.cancel(db,order_id)

@router.post("/orders/{order_id}/pay", response_model=PaymentOut)
def pay(order_id: str, request: PayRequest, db: Session = Depends(get_db)):
    return orders.pay(db,order_id,request)

@router.get("/orders/{order_id}/events", response_model=list[EventOut])
def events(order_id: str, db: Session = Depends(get_db)) -> list[dict]:
    orders.get_order(db,order_id)
    rows = db.scalars(select(AuditEvent).where(AuditEvent.order_id==order_id).order_by(AuditEvent.created_at,AuditEvent.id))
    return [{"id":e.id,"event":e.event,"created_at":utc_iso(e.created_at)} for e in rows]
