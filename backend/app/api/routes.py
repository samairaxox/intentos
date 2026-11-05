import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import PurchaseSession, Product, AuditEvent, Payment
from app.models.schemas import AnalyzeRequest, CreateOrder, Approval, PayRequest, OrderOut, PaymentOut, CatalogProduct, PurchaseOut, EventOut
from app.services.catalog import LocalCatalogProvider
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
    try:
        result = build_workflow(ai, LocalCatalogProvider(db)).invoke({"text":request.text})
    except AIUnavailable as exc:
        logger.warning('gemini_unavailable')
        raise HTTPException(503,str(exc)) from exc
    result.pop("products",None); result.pop("eligible",None)
    session = PurchaseSession(request=request.text,result=result)
    db.add(session); db.commit()
    logger.info('purchase_analyzed', extra={"session_id":session.id,"workflow_status":result["status"]})
    return {"id":session.id,**result}

@router.get("/purchases/{session_id}", response_model=PurchaseOut)
def purchase(session_id: str, db: Session = Depends(get_db)) -> dict:
    session = db.get(PurchaseSession,session_id)
    if not session: raise HTTPException(404,"Purchase session not found")
    return {"id":session.id,**session.result}

@router.post("/orders", response_model=OrderOut, status_code=201)
def create(request: CreateOrder, db: Session = Depends(get_db)):
    return orders.create_order(db,request)

@router.get("/orders/{order_id}", response_model=OrderOut)
def read_order(order_id: str, db: Session = Depends(get_db)):
    order = orders.get_order(db,order_id)
    payment = db.scalar(select(Payment).where(Payment.order_id==order_id))
    return {**OrderOut.model_validate(order).model_dump(), "payment":PaymentOut.model_validate(payment) if payment else None}

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
    return [{"id":e.id,"event":e.event,"created_at":e.created_at.isoformat()} for e in rows]
