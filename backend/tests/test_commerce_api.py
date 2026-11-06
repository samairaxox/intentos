from decimal import Decimal
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.api.commerce_routes import get_commerce_ai
from app.commerce.schemas import CommerceIntent,PreferencePatch
from app.commerce.payments import PaymentExecutionService
from app.commerce.tracing import TraceRecorder
from app.models.commerce import MockProviderReceipt,WorkflowTrace
from app.services.gemini import AIUnavailable
from test_api import client


def shopping_intent():return {'total_budget':100000,'items':[{'category':c,'priority':5 if c=='laptop' else 3} for c in ['laptop','monitor','keyboard','mouse','headphones']]}


def prepared(client):
    response=client.post('/api/v1/commerce/sessions',json={'intent':shopping_intent()})
    assert response.status_code==201,response.text
    result=response.json()
    purchase=client.post('/api/v1/commerce/purchases',json={'plan_id':result['plan']['id'],'idempotency_key':'commerce-purchase-key'})
    assert purchase.status_code==201,purchase.text
    return result,purchase.json(),'/api/v1/commerce/purchases/'+purchase.json()['id']


def test_provider_provenance_and_breakdowns(client):
    providers=client.get('/api/v1/commerce/providers').json()
    assert providers['live_integration'].startswith('pending') and providers['payment_provider']=='mock'
    result=client.get('/api/v1/commerce/offers?category=laptop').json()
    assert len(result['products'])==22 and len(result['offers'])==44
    assert all(row['offer']['source_type']=='demo' and row['freshness']['label']=='Demo offer' for row in result['offers'])
    assert all(Decimal(row['pricing']['final_price'])==Decimal(row['pricing']['base_price'])-Decimal(row['pricing']['confirmed_discount'])+Decimal(row['pricing']['shipping'])+Decimal(row['pricing']['fees']) for row in result['offers'])


def test_multi_merchant_execution_graph_and_partial_failure(client):
    result,purchase,path=prepared(client)
    assert len(purchase['suborders'])>=2
    assert client.post(path+'/execute',json={'idempotency_key':'execute-commerce-key'}).status_code==409
    assert client.post(path+'/approve',json={'approved':True}).status_code==200
    failing=purchase['suborders'][1]['merchant_id']
    response=client.post(path+'/execute',json={'idempotency_key':'execute-commerce-key','simulations':{failing:'failure'}})
    assert response.status_code==200,response.text
    assert response.json()['status']=='PARTIAL_FAILURE'
    assert response.json()['workflow']['action_required'].startswith('REVIEW_PARTIAL')
    assert any(s['status']=='CAPTURED' for s in response.json()['suborders'])
    traces=client.get('/api/v1/commerce/sessions/'+result['session']['id']+'/traces').json()
    assert any(t['node']=='verify_result' for t in traces)
    assert all(t['created_at'].endswith('+00:00') for t in traces)
    assert all('api_key' not in str(t['details']) for t in traces)
    pending=client.post(path+'/compensate',json={'pending':True})
    assert pending.json()['status']=='COMPENSATION_PENDING'
    assert client.post(path+'/compensate',json={}).json()['status']=='COMPENSATED'


@pytest.mark.parametrize('change',['price_increase','price_decrease','out_of_stock','merchant_unavailable','expired'])
def test_material_terms_require_fresh_approval(client,change):
    result,purchase,path=prepared(client)
    client.post(path+'/approve',json={'approved':True})
    offer_id=purchase['snapshot']['items'][0]['offer']['id']
    assert client.post('/api/v1/commerce/demo/offers/change',json={'offer_id':offer_id,'change':change}).status_code==200
    response=client.post(path+'/execute',json={'idempotency_key':'changed-commerce-execution'})
    assert response.status_code==409,response.text
    revised_id=response.json()['detail']['revised_plan_id']
    revised=client.get('/api/v1/commerce/plans/'+revised_id).json()
    assert revised['version']==2 and revised['changes']
    assert client.get(path).json()['status']=='APPROVAL_INVALIDATED'
    with client.factory() as db:assert not list(db.scalars(select(MockProviderReceipt)))
    new=client.post('/api/v1/commerce/purchases',json={'plan_id':revised_id,'idempotency_key':'fresh-commerce-key'})
    assert new.status_code==201,new.text
    assert new.json()['status']=='PENDING_APPROVAL'


def test_unknown_outcome_reconciliation_is_not_a_retry(client):
    _,purchase,path=prepared(client)
    client.post(path+'/approve',json={'approved':True})
    merchant=purchase['suborders'][0]['merchant_id']
    request={'idempotency_key':'unknown-commerce-execution','simulations':{merchant:'timeout_captured'}}
    response=client.post(path+'/execute',json=request)
    assert response.json()['status']=='PAYMENT_UNKNOWN'
    assert response.json()['workflow']['action_required']=='RECONCILE_WITH_PROVIDER_BEFORE_RETRY'
    assert client.post(path+'/reconcile',json={}).status_code==200
    resumed=client.post(path+'/execute',json=request)
    assert resumed.status_code==200,resumed.text
    assert resumed.json()['status']=='PAID'
    again=client.post(path+'/execute',json=request)
    assert again.json()['status']=='PAID'
    assert all(len(s['attempts'])==1 for s in again.json()['suborders'])


def test_unresolved_demo_outcome_and_confirmed_retry(client,monkeypatch):
    monkeypatch.setattr(PaymentExecutionService,'retry_delay',timedelta(0))
    _,purchase,path=prepared(client)
    client.post(path+'/approve',json={'approved':True})
    first=purchase['suborders'][0]
    request={'idempotency_key':'unresolved-commerce-execution','simulations':{first['merchant_id']:'timeout_unknown'}}
    unknown=client.post(path+'/execute',json=request).json()
    sub=next(s for s in unknown['suborders'] if s['id']==first['id'])
    assert client.post('/api/v1/commerce/suborders/'+sub['id']+'/retry',json={'idempotency_key':'premature-retry-key'}).status_code==409
    attempt=sub['attempts'][-1]['id']
    assert client.post('/api/v1/commerce/demo/attempts/'+attempt+'/resolve',json={'outcome':'FAILED'}).status_code==200
    reconciled=client.post(path+'/reconcile',json={})
    assert reconciled.status_code==200 and reconciled.json()['status']=='PARTIAL_FAILURE'
    retried=client.post('/api/v1/commerce/suborders/'+sub['id']+'/retry',json={'idempotency_key':'confirmed-retry-key'})
    assert retried.status_code==200,retried.text
    assert client.post(path+'/execute',json=request).json()['status']=='PAID'


def test_session_memory_natural_update_and_resume(client):
    class FakeAI:
        def parse(self,text):return CommerceIntent.model_validate(shopping_intent())
        def patch(self,text,intent):return PreferencePatch(weights={'portability':5})
        def explain(self,combinations):return combinations
    client.app.dependency_overrides[get_commerce_ai]=lambda:FakeAI()
    result=client.post('/api/v1/commerce/sessions',json={'text':'Build a coding workstation under 100000'}).json()
    session=result['session'];plan=result['plan']
    response=client.post('/api/v1/commerce/sessions/'+session['id']+'/preferences',json={'expected_version':1,'text':'Actually I prefer something lighter'})
    assert response.status_code==201,response.text
    current=response.json()
    assert current['session']['intent']['total_budget']==100000
    assert current['session']['intent']['weights']['portability']==5
    assert len(current['session']['conversation'])==2
    resumed=client.post('/api/v1/commerce/plans/'+current['plan']['id']+'/resume',json={})
    assert resumed.json()['id']==current['plan']['id'] and resumed.json()['status']=='AWAITING_SELECTION'
    assert client.post('/api/v1/commerce/plans/'+plan['id']+'/resume',json={}).status_code==409


def test_ai_failure_retains_resumable_session(client):
    class Offline:
        def parse(self,text):raise AIUnavailable('Gemini unavailable during test')
    client.app.dependency_overrides[get_commerce_ai]=lambda:Offline()
    response=client.post('/api/v1/commerce/sessions',json={'text':'Find a laptop under 75000 with good battery'})
    assert response.status_code==503
    detail=response.json()['detail'];assert detail['session_id'] and detail['plan_id']
    assert client.get('/api/v1/commerce/plans/'+detail['plan_id']).json()['status']=='INTERRUPTED'
    class Online:
        def parse(self,text):return CommerceIntent(total_budget=75000,items=[{'category':'laptop'}])
        def explain(self,combinations):return combinations
    client.app.dependency_overrides[get_commerce_ai]=lambda:Online()
    resumed=client.post('/api/v1/commerce/plans/'+detail['plan_id']+'/resume',json={})
    assert resumed.status_code==200,resumed.text
    assert resumed.json()['status']=='AWAITING_SELECTION'


def test_rejection_amount_tampering_and_trace_redaction(client):
    result,purchase,path=prepared(client)
    assert client.post(path+'/approve',json={'approved':True,'amount':'0.01'}).status_code==422
    assert client.post(path+'/reject',json={}).json()['status']=='REJECTED'
    assert client.post(path+'/execute',json={'idempotency_key':'rejected-execution-key'}).json()['status']=='REJECTED'
    with client.factory() as db:
        TraceRecorder(db,result['plan']['id'],result['session']['id']).record('test','COMPLETED',{'state':'CAPTURED','api_key':'do-not-store','card_number':'do-not-store','duration_ms':1.0});db.commit()
    traces=client.get('/api/v1/commerce/sessions/'+result['session']['id']+'/traces').json()
    assert all('do-not-store' not in str(t) for t in traces)
