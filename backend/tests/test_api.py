import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.db.session import get_db
from app.api.routes import get_ai
from app.models.entities import Base, Product, Payment
from app.models.schemas import Intent, Constraint
from app.services.catalog import seed
from app.services.gemini import AIUnavailable
from test_workflow import FakeAI

@pytest.fixture
def client():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    with factory() as db: seed(db)
    def database():
        with factory() as db: yield db
    app.dependency_overrides[get_db]=database
    app.dependency_overrides[get_ai]=lambda:FakeAI(Intent(category="laptop",max_budget=75000,required_specifications=[Constraint(field="ram_gb",operator="min",value=16),Constraint(field="processor_brand",operator="eq",value="Intel")]))
    with TestClient(app) as client:
        client.factory=factory
        yield client
    app.dependency_overrides.clear()
    engine.dispose()

def make_order(client,key="order-key-001"):
    result=client.post("/api/v1/purchases/analyze",json={"text":"Intel laptop under 75000 for coding"})
    assert result.status_code==201, result.text
    session=result.json()
    payload={"session_id":session["id"],"product_id":session["recommendations"][0]["product"]["id"],"idempotency_key":key}
    response=client.post("/api/v1/orders",json=payload)
    assert response.status_code==201, response.text
    return response.json(),payload

def test_health_catalog_and_session(client):
    assert client.get("/health").json()["status"]=="ok"
    assert len(client.get("/api/v1/products").json())==22
    order,payload=make_order(client)
    assert client.get('/api/v1/purchases/'+payload['session_id']).status_code==200
    assert client.get('/api/v1/orders/'+order['id']).json()['status']=='PENDING_APPROVAL'
    assert client.get('/api/v1/orders/missing').status_code==404

def test_approval_and_duplicate_payment(client):
    order,payload=make_order(client)
    assert client.post('/api/v1/orders',json=payload).json()['id']==order['id']
    path='/api/v1/orders/'+order['id']
    assert client.post(path+'/pay',json={'idempotency_key':'payment-key-1'}).status_code==409
    assert client.post(path+'/approve',json={'approved':False}).status_code==422
    assert client.post(path+'/approve',json={'approved':True}).json()['status']=='APPROVED'
    body={'idempotency_key':'payment-key-1'}
    first=client.post(path+'/pay',json=body)
    assert first.status_code==200,first.text
    assert first.json()['status']=='PAID'
    assert client.post(path+'/pay',json=body).json()['id']==first.json()['id']
    assert client.post(path+'/pay',json={'idempotency_key':'different-key'}).status_code==409
    assert client.post(path+'/approve',json={'approved':True}).status_code==409
    assert client.get(path).json()['status']=='PAID'
    assert client.get(path).json()['payment']['id']==first.json()['id']
    assert [e['event'] for e in client.get(path+'/events').json()]==['PENDING_APPROVAL','APPROVED','PAYMENT_PROCESSING','PAID']
    with client.factory() as db: assert len(list(db.scalars(select(Payment))))==1

def test_payment_failure_and_cancellation(client):
    order,_=make_order(client)
    path='/api/v1/orders/'+order['id']
    client.post(path+'/approve',json={'approved':True})
    response=client.post(path+'/pay',json={'idempotency_key':'failure-key','simulate_failure':True})
    assert response.json()['status']=='PAYMENT_FAILED'
    assert client.get(path).json()['status']=='PAYMENT_FAILED'
    assert client.post(path+'/cancel').status_code==409
    other,_=make_order(client,'order-key-002')
    assert client.post('/api/v1/orders/'+other['id']+'/cancel').json()['status']=='CANCELLED'
    assert client.post('/api/v1/orders/'+other['id']+'/approve',json={'approved':True}).status_code==409

@pytest.mark.parametrize('change',[{'available':False},{'price':999999},{'price':60001}])
def test_product_changes_block_checkout(client,change):
    order,payload=make_order(client)
    with client.factory() as db:
        product=db.get(Product,payload['product_id'])
        product.data={**product.data,**change}; db.commit()
    assert client.post('/api/v1/orders/'+order['id']+'/approve',json={'approved':True}).status_code==409

def test_ai_unavailable(client):
    class Unavailable:
        def parse(self,text): raise AIUnavailable('Gemini unavailable')
    app.dependency_overrides[get_ai]=lambda:Unavailable()
    response=client.post('/api/v1/purchases/analyze',json={'text':'A laptop request that needs AI'})
    assert response.status_code==503

def test_impossible_api(client):
    app.dependency_overrides[get_ai]=lambda:FakeAI(Intent(category='laptop',max_budget=1))
    response=client.post('/api/v1/purchases/analyze',json={'text':'Impossible laptop for one rupee'})
    assert response.json()['status']=='NO_MATCH'
    assert not response.json()['recommendations']

def test_reject_unrecommended_product_and_key_reuse(client):
    order,payload=make_order(client)
    assert client.post('/api/v1/orders',json={**payload,'product_id':'demo-22'}).status_code==409
    assert client.post('/api/v1/orders',json={**payload,'product_id':'demo-22','idempotency_key':'fresh-key'}).status_code==422


def test_cross_order_payment_key_conflict(client):
    first,_=make_order(client)
    second,_=make_order(client,'second-order-key')
    for order in [first,second]:
        assert client.post('/api/v1/orders/'+order['id']+'/approve',json={'approved':True}).status_code==200
    body={'idempotency_key':'shared-payment-key'}
    assert client.post('/api/v1/orders/'+first['id']+'/pay',json=body).status_code==200
    assert client.post('/api/v1/orders/'+second['id']+'/pay',json=body).status_code==409
    assert client.get('/api/v1/orders/'+second['id']).json()['status']=='APPROVED'

def test_unavailable_after_approval(client):
    order,payload=make_order(client)
    path='/api/v1/orders/'+order['id']
    client.post(path+'/approve',json={'approved':True})
    with client.factory() as db:
        product=db.get(Product,payload['product_id'])
        product.data={**product.data,'available':False};db.commit()
    assert client.post(path+'/pay',json={'idempotency_key':'unavailable-key'}).status_code==409
    assert client.get(path).json()['status']=='APPROVED'


def test_client_price_and_amount_rejected(client):
    order,payload=make_order(client)
    assert client.post('/api/v1/orders',json={**payload,'price':1}).status_code==422
    assert client.post('/api/v1/orders/'+order['id']+'/pay',json={'idempotency_key':'tamper-key','amount':1}).status_code==422
