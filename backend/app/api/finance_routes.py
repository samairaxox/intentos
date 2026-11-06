from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.finance import service
from app.finance.schemas import DecisionStart,DecisionUpdate,ScenarioSpec,StrategySelection
from app.finance.workflow import FinancialAI,run
from app.finance.history import history,seed_synthetic
from app.commerce.store import discover_and_persist
from app.commerce.ai import CommerceAI
from app.commerce.checkout import present_purchase
from app.services.gemini import AIUnavailable

router=APIRouter(prefix='/api/v1/finance',tags=['Financial intelligence'])
def get_financial_ai():return FinancialAI()


def invoke(fn,*args):
    try:return fn(*args)
    except AIUnavailable as exc:
        raise HTTPException(503,{'message':str(exc),'decision_id':getattr(exc,'financial_decision_id',None)}) from exc


@router.post('/decisions')
def create(request:DecisionStart,db:Session=Depends(get_db),ai=Depends(get_financial_ai)):
    return service.present(db,invoke(service.create,db,request,ai))


@router.get('/decisions/{decision_id}')
def get(decision_id:str,db:Session=Depends(get_db)):
    return service.present(db,service.decision_for(db,decision_id))


@router.post('/decisions/{decision_id}/resume')
def resume(decision_id:str,db:Session=Depends(get_db),ai=Depends(get_financial_ai)):
    decision=service.decision_for(db,decision_id);service.assert_latest(db,decision)
    return service.present(db,invoke(run,db,decision,ai))


@router.post('/decisions/{decision_id}/revise')
def revise(decision_id:str,request:DecisionUpdate,db:Session=Depends(get_db),ai=Depends(get_financial_ai)):
    return service.present(db,invoke(service.revise,db,service.decision_for(db,decision_id),request.goal,ai))


@router.post('/decisions/{decision_id}/replan')
def replan(decision_id:str,db:Session=Depends(get_db),ai=Depends(get_financial_ai)):
    from app.finance.schemas import FinancialGoal
    old=service.decision_for(db,decision_id)
    if not old.goal:raise HTTPException(422,"No parsed goal; resume or submit a revised goal")
    return service.present(db,invoke(service.revise,db,old,FinancialGoal.model_validate(old.goal),ai))


@router.post('/decisions/{decision_id}/select')
def select(decision_id:str,request:StrategySelection,db:Session=Depends(get_db)):
    purchase=service.select_strategy(db,service.decision_for(db,decision_id),request,CommerceAI())
    return present_purchase(db,purchase)


@router.post('/decisions/{decision_id}/scenarios')
def scenario(decision_id:str,request:ScenarioSpec,db:Session=Depends(get_db)):
    return service.scenario(db,service.decision_for(db,decision_id),request)


@router.get('/history/{offer_id}')
def observations(offer_id:str,mode:str='recorded',db:Session=Depends(get_db)):
    if mode not in ['recorded','synthetic_demo']:raise HTTPException(422,'Invalid history mode')
    return history(db,offer_id,mode)


@router.post('/demo/synthetic-history')
def synthetic_history(db:Session=Depends(get_db)):
    found=discover_and_persist(db,['laptop','monitor','keyboard','mouse','headphones'])
    count=seed_synthetic(db,found.offers);db.commit()
    return {'created':count,'source':'synthetic_fixture_v1','warning':'Synthetic development prices; never genuine market history. Use history_mode synthetic_demo explicitly.'}
