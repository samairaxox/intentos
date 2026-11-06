from decimal import Decimal
from sqlalchemy import select
from test_api import client
from app.main import app
from app.api.finance_routes import get_financial_ai
from app.finance.schemas import FinancialGoal
from app.finance.workflow import FinancialAI
from app.models.commerce import PaymentAttempt,CommercePurchase,ProductOffer
from app.models.finance import FinancialDecision
from app.services.gemini import AIUnavailable


def goal(**changes):
    return {'total_budget':'100000.00','mandatory_reserve':'10000.00','patience_days':14,
        'items':[{'category':'laptop','hard_constraints':[{'field':'ram_gb','operator':'min','value':16}]},{'category':'monitor'}],**changes}


def decision(client,**changes):
    response=client.post('/api/v1/finance/decisions',json={'goal':goal(**changes)})
    assert response.status_code==200,response.text
    return response.json()


def purchase(client,d,key='financial-purchase-001'):
    response=client.post(f"/api/v1/finance/decisions/{d['id']}/select",json={'strategy':'optimized','idempotency_key':key})
    assert response.status_code==200,response.text
    return response.json()


def test_checkpoint_resume_reserve_and_explicit_approval(client):
    d=decision(client)
    assert len(d['workflow']['completed'])==10 and d['result']['reserve']['spendable']=='90000.00'
    resumed=client.post(f"/api/v1/finance/decisions/{d['id']}/resume").json()
    assert resumed['result']==d['result']
    p=purchase(client,d)
    assert Decimal(p['amount'])<=90000 and p['status']=='PENDING_APPROVAL'
    path='/api/v1/commerce/purchases/'+p['id']
    assert client.post(path+'/execute',json={'idempotency_key':'finance-execute-001'}).status_code==409
    with client.factory() as db: assert not list(db.scalars(select(PaymentAttempt)))
    assert client.post(path+'/approve',json={'approved':True}).status_code==200
    assert client.post(path+'/execute',json={'idempotency_key':'finance-execute-001'}).json()['status']=='PAID'
    restored=client.get('/api/v1/finance/decisions/'+d['id']).json()
    assert p['id'] in restored['purchase_ids']
    # A second charge cannot spend the envelope a second time.
    another=client.post(f"/api/v1/finance/decisions/{d['id']}/select",json={'strategy':'optimized','idempotency_key':'financial-purchase-002'})
    assert another.status_code==409
    replanned=client.post(f"/api/v1/finance/decisions/{d['id']}/replan").json()
    assert replanned['result']['reserve']['encumbered']==p['amount']
    assert replanned['result']['status']=='NO_MATCH'


def test_budget_revision_invalidates_approval_and_blocks_commerce_bypass(client):
    d=decision(client);p=purchase(client,d)
    path='/api/v1/commerce/purchases/'+p['id']
    assert client.post(path+'/approve',json={'approved':True}).status_code==200
    revised=client.post(f"/api/v1/finance/decisions/{d['id']}/revise",json={'goal':goal(total_budget='95000')})
    assert revised.status_code==200,revised.text
    assert client.get(path).json()['status']=='APPROVAL_INVALIDATED'
    assert client.post(path+'/execute',json={'idempotency_key':'revised-execute-001'}).status_code==409
    bypass=client.post(f"/api/v1/commerce/sessions/{d['session_id']}/preferences",json={'expected_version':1,'patch':{'total_budget':200000}})
    assert bypass.status_code==409
    assert client.post(f"/api/v1/commerce/plans/{p['plan_id']}/replan").status_code==409
    with client.factory() as db: assert not list(db.scalars(select(PaymentAttempt)))


def test_material_quote_change_requires_new_financial_decision(client):
    d=decision(client);p=purchase(client,d)
    path='/api/v1/commerce/purchases/'+p['id']
    client.post(path+'/approve',json={'approved':True})
    offer_id=p['snapshot']['items'][0]['offer']['id']
    client.post('/api/v1/commerce/demo/offers/change',json={'offer_id':offer_id,'change':'price_increase'})
    executed=client.post(path+'/execute',json={'idempotency_key':'quote-change-execute'})
    assert executed.status_code==409,executed.text
    assert executed.json()['detail']['revised_decision_id']!=d['id']
    assert client.get(path).json()['status']=='APPROVAL_INVALIDATED'


def test_hypothetical_history_and_selection_safety(client):
    d=decision(client)
    selected=d['result']['strategies'][2]['plan']['items'][0]['offer']['id']
    before=client.get('/api/v1/finance/history/'+selected).json()
    scenario=client.post(f"/api/v1/finance/decisions/{d['id']}/scenarios",json={'category_price_change_percent':{'laptop':'10'},'budget_reduction':'15000'}).json()
    assert scenario['result']['hypothetical'] and scenario['result']['reserve']['spendable']=='75000.00'
    assert before==client.get('/api/v1/finance/history/'+selected).json()
    assert client.get('/api/v1/finance/decisions/'+d['id']).json()['result']==d['result']
    assert client.post(f"/api/v1/finance/decisions/{d['id']}/select",json={'strategy':'wait','idempotency_key':'invalid-wait-purchase'}).status_code==422
    response=client.post('/api/v1/finance/demo/synthetic-history')
    assert response.status_code==200 and response.json()['created']>0
    assert client.get('/api/v1/finance/history/'+selected).json()['count']==before['count']
    assert client.get('/api/v1/finance/history/'+selected+'?mode=synthetic_demo').json()['count']==14


def test_ai_interruption_resumes_and_uses_validated_goal(client):
    class Broken:
        def parse(self,text):raise AIUnavailable('fixture unavailable')
    app.dependency_overrides[get_financial_ai]=lambda:Broken()
    response=client.post('/api/v1/finance/decisions',json={'text':'Coding setup under one lakh, reserve ten thousand'})
    assert response.status_code==503 and response.json()['detail']['decision_id']
    did=response.json()['detail']['decision_id']
    restored=client.get(f'/api/v1/finance/decisions/{did}').json()
    assert restored['goal'] is None and restored['result']['strategies']==[]
    assert restored['status']=='INTERRUPTED'
    assert client.post(f'/api/v1/finance/decisions/{did}/replan').status_code==422
    class FixtureAI:
        def parse(self,text):return FinancialGoal.model_validate(goal())
        def explain(self,strategies):return strategies
    app.dependency_overrides[get_financial_ai]=lambda:FixtureAI()
    resumed=client.post(f'/api/v1/finance/decisions/{did}/resume')
    assert resumed.status_code==200,resumed.text
    assert resumed.json()['status']=='AWAITING_DECISION'


def test_optional_only_goal_requires_clarification_before_payment(client):
    d=decision(client,risk_strategy='cost_focused',items=[{'category':'headphones','required':False}])
    assert d['result']['strategies']==[]
    assert 'at least one required category' in d['result']['missing_information']
    selected=client.post(f"/api/v1/finance/decisions/{d['id']}/select",json={'strategy':'optimized','idempotency_key':'empty-optional-key'})
    assert selected.status_code==409
    with client.factory() as db:assert not list(db.scalars(select(CommercePurchase)))
