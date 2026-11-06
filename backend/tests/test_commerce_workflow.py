from decimal import Decimal
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.models.entities import Base
from app.models.commerce import WorkflowTrace,CommerceSession,ProductOffer
from app.commerce.schemas import SessionStart,SessionUpdate,CommerceIntent,PreferencePatch
from app.commerce.sessions import create_session,update_session,merge_preferences,present_plan,ensure_current
from app.commerce.workflow import run_planning
from app.commerce.ai import CommerceAI
from app.services.catalog import seed
from fastapi import HTTPException

@pytest.fixture
def db():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with sessionmaker(engine,expire_on_commit=False)() as db:
        seed(db);yield db
    engine.dispose()

def intent():return CommerceIntent(total_budget=100000,items=[{'category':'laptop','hard_constraints':[{'field':'ram_gb','operator':'min','value':16}]},{'category':'monitor'}])

def test_persisted_graph_and_resume(db):
    session,plan=create_session(db,SessionStart(intent=intent()),CommerceAI())
    assert plan.status=='AWAITING_SELECTION'
    assert 'retrieve_offers' in plan.workflow['completed']
    trace_count=len(list(db.scalars(select(WorkflowTrace))))
    run_planning(db,plan,CommerceAI())
    assert len(list(db.scalars(select(WorkflowTrace))))==trace_count
    assert present_plan(db,plan)['result']['combinations']

def test_session_patch_retains_budget_and_other_constraints(db):
    session,plan=create_session(db,SessionStart(intent=intent()),CommerceAI())
    patch=PreferencePatch(weights={'portability':5},items=[{'category':'laptop','soft_preferences':[{'field':'weight_kg','operator':'max','value':1.4}]}])
    revised=update_session(db,session.id,SessionUpdate(expected_version=1,patch=patch),CommerceAI())
    assert revised.parent_id==plan.id and revised.version==2
    assert revised.intent['total_budget']==100000
    assert revised.intent['items'][0]['hard_constraints']==plan.intent['items'][0]['hard_constraints']
    assert revised.intent['weights']['portability']==5
    assert db.get(CommerceSession,session.id).conversation[-1]['patch']
    with pytest.raises(HTTPException) as error:update_session(db,session.id,SessionUpdate(expected_version=1,patch=patch),CommerceAI())
    assert error.value.status_code==409

def test_material_change_replans_same_session(db):
    session,plan=create_session(db,SessionStart(intent=intent()),CommerceAI())
    combo=plan.result['combinations'][0]
    row=db.get(ProductOffer,combo['items'][0]['offer']['id'])
    row.data={**row.data,'base_price':format(Decimal(row.data['base_price'])+Decimal('4000.00'),'.2f')};db.commit()
    with pytest.raises(HTTPException) as error:ensure_current(db,plan,combo,CommerceAI())
    assert error.value.status_code==409 and error.value.detail['revised_plan_id']
    assert plan.status=='INVALIDATED'

def test_independent_sessions_do_not_share_memory(db):
    a,pa=create_session(db,SessionStart(intent=intent()),CommerceAI())
    b,pb=create_session(db,SessionStart(intent=CommerceIntent(total_budget=75000,items=[{'category':'laptop'}])),CommerceAI())
    update_session(db,a.id,SessionUpdate(expected_version=1,patch={'weights':{'portability':5}}),CommerceAI())
    assert b.intent['total_budget']==75000 and b.version==1 and b.intent['weights']['portability']==1
