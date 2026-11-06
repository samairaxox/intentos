from app.core.time import utc_iso
from datetime import timedelta
from decimal import Decimal
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.commerce import ProductOffer,Merchant,WorkflowTrace
from app.models.schemas import Approval
from app.commerce.schemas import (SessionStart,SessionUpdate,PurchaseCreate,ExecuteRequest,RetryRequest,OfferChange,DemoResolution,CompensationRequest,RefreshRequest,SessionResult,SessionView,PlanView,PurchaseView,utc)
from app.commerce.ai import CommerceAI
from app.commerce import sessions,checkout
from app.commerce.store import discover_and_persist,registry_for
from app.commerce.freshness import OfferFreshnessService
from app.commerce.pricing import TotalCostService
from app.commerce.schemas import MerchantOffer
from app.commerce.payments import PaymentAuthorizationService,PaymentExecutionService,PaymentReconciliationService,purchase_for
from app.commerce.execution_workflow import execute_checkout_graph
from app.commerce.workflow import run_planning
from app.services.gemini import AIUnavailable

router=APIRouter(prefix='/api/v1/commerce',tags=['Commerce Phase 3'])

def get_commerce_ai():return CommerceAI()

def ai_call(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except AIUnavailable as exc:
        raise HTTPException(503,{'message':str(exc),'session_id':getattr(exc,'commerce_session_id',None),'plan_id':getattr(exc,'commerce_plan_id',None)}) from exc

@router.get('/providers')
def providers(db:Session=Depends(get_db))->dict:
    return {'commerce':registry_for(db).status(),'live_integration':'pending_authorized_provider_and_official_adapter','payment_provider':'mock','sandbox_integration':'not_configured','public_deployment_supported':False}

@router.get('/offers')
def offers(category:str | None=None,db:Session=Depends(get_db))->dict:
    categories=[category] if category else ['laptop','monitor','keyboard','mouse','headphones']
    found=discover_and_persist(db,categories);by_id={p.id:p.model_dump(mode='json') for p in found.products}
    db.commit()
    return {'products':list(by_id.values()),'offers':[{'offer':o.model_dump(mode='json'),'product':by_id[o.product_id],'pricing':TotalCostService().calculate(o),'freshness':OfferFreshnessService().inspect(o)} for o in found.offers],'warnings':found.warnings,'live_integration':'pending'}

@router.post('/offers/refresh')
def refresh(request:RefreshRequest,db:Session=Depends(get_db))->dict:
    rows=list(db.scalars(select(ProductOffer).order_by(ProductOffer.id).with_for_update()))
    changed=[]
    for row in rows:
        if request.offer_ids and row.id not in request.offer_ids:continue
        if row.data['source_type']!='demo':continue
        at=utc();row.data={**row.data,'retrieved_at':at.isoformat(),'expires_at':(at+timedelta(minutes=15)).isoformat()};row.revision+=1;changed.append(row.id)
    db.commit();return {'refreshed':changed,'source_type':'demo','message':'Current local demo terms re-quoted. This is not live merchant verification.'}

@router.post('/sessions',response_model=SessionResult,status_code=201)
def create_session(request:SessionStart,db:Session=Depends(get_db),ai=Depends(get_commerce_ai)):
    session,plan=ai_call(sessions.create_session,db,request,ai)
    return {'session':sessions.present_session(db,session),'plan':sessions.present_plan(db,plan)}

@router.get('/sessions/{session_id}',response_model=SessionView)
def read_session(session_id:str,db:Session=Depends(get_db)):
    return sessions.present_session(db,sessions.session_for(db,session_id))

@router.post('/sessions/{session_id}/preferences',response_model=SessionResult,status_code=201)
def update(session_id:str,request:SessionUpdate,db:Session=Depends(get_db),ai=Depends(get_commerce_ai)):
    plan=ai_call(sessions.update_session,db,session_id,request,ai)
    return {'session':sessions.present_session(db,sessions.session_for(db,session_id)),'plan':sessions.present_plan(db,plan)}

@router.get('/plans/{plan_id}',response_model=PlanView)
def read_plan(plan_id:str,db:Session=Depends(get_db)):
    return sessions.present_plan(db,sessions.plan_for(db,plan_id))

@router.post('/plans/{plan_id}/resume',response_model=PlanView)
def resume(plan_id:str,db:Session=Depends(get_db),ai=Depends(get_commerce_ai)):
    plan=sessions.plan_for(db,plan_id);session=sessions.session_for(db,plan.session_id)
    if plan.id!=session.latest_plan_id or plan.status=='INVALIDATED':raise HTTPException(409,{'message':'Resume the latest plan','revised_plan_id':session.latest_plan_id})
    ai_call(run_planning,db,plan,ai);session.intent=plan.intent;sessions.save_snapshots(db,plan);db.commit()
    return sessions.present_plan(db,plan)

@router.post('/plans/{plan_id}/replan',response_model=SessionResult,status_code=201)
def replan(plan_id:str,db:Session=Depends(get_db),ai=Depends(get_commerce_ai)):
    plan=ai_call(sessions.replan,db,sessions.plan_for(db,plan_id),ai)
    return {'session':sessions.present_session(db,sessions.session_for(db,plan.session_id)),'plan':sessions.present_plan(db,plan)}

@router.post('/plans/{plan_id}/validate')
def validate(plan_id:str,alternative_index:int=0,db:Session=Depends(get_db),ai=Depends(get_commerce_ai))->dict:
    plan=sessions.plan_for(db,plan_id);choices=plan.result.get('combinations',[])
    if alternative_index<0 or alternative_index>=len(choices):raise HTTPException(422,'Unknown plan alternative')
    ai_call(sessions.ensure_current,db,plan,choices[alternative_index],ai)
    return {'valid':True,'plan_id':plan.id}

@router.post('/purchases',response_model=PurchaseView,status_code=201)
def create_purchase(request:PurchaseCreate,db:Session=Depends(get_db),ai=Depends(get_commerce_ai)):
    return checkout.present_purchase(db,ai_call(checkout.create_purchase,db,request,ai))

@router.get('/purchases/{purchase_id}',response_model=PurchaseView)
def read_purchase(purchase_id:str,db:Session=Depends(get_db)):
    row,_=purchase_for(db,purchase_id);return checkout.present_purchase(db,row)

@router.post('/purchases/{purchase_id}/approve',response_model=PurchaseView)
def approve(purchase_id:str,request:Approval,db:Session=Depends(get_db),ai=Depends(get_commerce_ai)):
    return checkout.present_purchase(db,ai_call(PaymentAuthorizationService().approve,db,purchase_id,ai))

@router.post('/purchases/{purchase_id}/reject',response_model=PurchaseView)
def reject(purchase_id:str,db:Session=Depends(get_db)):
    return checkout.present_purchase(db,checkout.reject(db,purchase_id))

@router.post('/purchases/{purchase_id}/execute',response_model=PurchaseView)
def execute(purchase_id:str,request:ExecuteRequest,db:Session=Depends(get_db),ai=Depends(get_commerce_ai)):
    return checkout.present_purchase(db,ai_call(execute_checkout_graph,db,purchase_id,request,ai))

@router.post('/purchases/{purchase_id}/reconcile',response_model=PurchaseView)
def reconcile(purchase_id:str,db:Session=Depends(get_db)):
    return checkout.present_purchase(db,PaymentReconciliationService().reconcile(db,purchase_id))

@router.post('/purchases/{purchase_id}/compensate',response_model=PurchaseView)
def compensate(purchase_id:str,request:CompensationRequest,db:Session=Depends(get_db)):
    return checkout.present_purchase(db,PaymentReconciliationService().compensate(db,purchase_id,request.pending))

@router.post('/suborders/{suborder_id}/retry',response_model=PurchaseView)
def retry(suborder_id:str,request:RetryRequest,db:Session=Depends(get_db),ai=Depends(get_commerce_ai)):
    return checkout.present_purchase(db,ai_call(PaymentExecutionService().retry,db,suborder_id,request,ai))

@router.post('/demo/attempts/{attempt_id}/resolve')
def resolve(attempt_id:str,request:DemoResolution,db:Session=Depends(get_db))->dict:
    return checkout.resolve_demo_outcome(db,attempt_id,request.outcome)

@router.post('/demo/offers/change')
def change_offer(request:OfferChange,db:Session=Depends(get_db))->dict:
    row=db.scalar(select(ProductOffer).where(ProductOffer.id==request.offer_id).with_for_update())
    if not row or row.data['source_type']!='demo':raise HTTPException(422,'Only an existing demo offer may be simulated')
    update={}
    if request.change=='merchant_unavailable':db.get(Merchant,row.merchant_id).available=False
    elif request.change=='out_of_stock':update={'available':False,'stock':0}
    elif request.change=='expired':update={'expires_at':(utc()-timedelta(seconds=1)).isoformat()}
    else:
        delta=Decimal('4000.00') if request.change=='price_increase' else Decimal('-1000.00')
        update={'base_price':format(max(Decimal('1.00'),Decimal(row.data['base_price'])+delta),'.2f')}
    row.data={**row.data,**update};row.revision+=1;db.commit()
    return {'offer_id':row.id,'change':request.change,'message':'Demo terms changed. Validation or checkout will require fresh approval.'}

@router.get('/sessions/{session_id}/traces')
def traces(session_id:str,db:Session=Depends(get_db))->list[dict]:
    sessions.session_for(db,session_id)
    records=db.scalars(select(WorkflowTrace).where(WorkflowTrace.session_id==session_id).order_by(WorkflowTrace.created_at,WorkflowTrace.id))
    return [{'id':r.id,'workflow_id':r.workflow_id,'session_id':r.session_id,'node':r.node,'status':r.status,'details':r.details,'created_at':utc_iso(r.created_at)} for r in records]
