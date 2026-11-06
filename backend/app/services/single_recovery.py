from sqlalchemy.exc import SQLAlchemyError
from app.models.entities import PurchaseSession
from app.agents.workflow import build_workflow
from app.agents.checkpoints import rediscover_after_interruption,PlanningInterrupted
from app.services.gemini import AIUnavailable
from fastapi import HTTPException
import logging
from app.services.catalog import LocalCatalogProvider


def present(session):
    result=session.result
    recommendations=result.get('recommendations',[])
    if result.get('status') in ['INTERRUPTED','PLANNING']:
        recommendations=[{**r,'explanation':r.get('explanation','Explanation not completed; resume the interrupted workflow.')} for r in recommendations]
    return {'id':session.id,'text':session.request,'status':result.get('status','INTERRUPTED'),
        'intent':result.get('intent') or {'category':'unknown','missing_essential_details':['Intent parsing has not completed']},
        'recommendations':recommendations,'steps':result.get('steps',[])}


def run(db,session,ai,resume=False):
    state=session.result.get('workflow',{'text':session.request,'steps':[],'completed':[]})
    if resume:
        if session.result.get('status') not in ['INTERRUPTED','PLANNING']:return session
        state=rediscover_after_interruption(state,'parser','validator')
    def save(s):
        session.result={'kind':'single','status':s.get('status','PLANNING'),**{k:v for k,v in s.items() if k not in ['products','eligible']},'workflow':s}
        db.commit()
    try:build_workflow(ai,LocalCatalogProvider(db),checkpoint=save).invoke(state)
    except SQLAlchemyError:
        db.rollback();raise
    except Exception as exc:
        db.rollback();session.result={**session.result,'status':'INTERRUPTED'};db.commit()
        if isinstance(exc,HTTPException):raise
        logging.getLogger(__name__).error('single_planning_interrupted: %s',type(exc).__name__)
        error=exc if isinstance(exc,AIUnavailable) else PlanningInterrupted('Purchase planning interrupted; resume the saved session')
        setattr(error,'purchase_session_id',session.id);raise error from exc
    return session


def create(db,text,ai):
    session=PurchaseSession(request=text,result={'kind':'single','status':'PLANNING','workflow':{'text':text,'steps':[],'completed':[]}})
    db.add(session);db.commit()
    return run(db,session,ai)
