from fastapi.testclient import TestClient
from sqlalchemy import select
from test_api import client,make_order
from app.main import app
from app.models.entities import PurchaseSession


def test_cross_user_root_order_and_creation_denied(client):
    order,payload=make_order(client,'ownership-order-001')
    with TestClient(app,headers={'Authorization':'Bearer test-owner-token-00000000000000000002'}) as other:
        for path in ['/api/v1/orders/'+order['id'],'/api/v1/purchases/'+payload['session_id']]:
            assert other.get(path).status_code==404
        assert other.post('/api/v1/orders/'+order['id']+'/approve',json={'approved':True}).status_code==404
        assert other.post('/api/v1/orders',json={**payload,'idempotency_key':'other-owner-attempt'}).status_code==404
    with client.factory() as db:assert db.get(PurchaseSession,payload['session_id']).owner_id=='user-a'


def test_commerce_children_cannot_bypass_ownership(client):
    result=client.post('/api/v1/commerce/sessions',json={'intent':{'total_budget':75000,'items':[{'category':'laptop'}]}}).json()
    purchase=client.post('/api/v1/commerce/purchases',json={'plan_id':result['plan']['id'],'idempotency_key':'owned-commerce-purchase'}).json()
    with TestClient(app,headers={'Authorization':'Bearer test-owner-token-00000000000000000002'}) as other:
        assert other.get('/api/v1/commerce/purchases/'+purchase['id']).status_code==404
        assert other.post('/api/v1/commerce/suborders/'+purchase['suborders'][0]['id']+'/retry',json={'idempotency_key':'cross-owner-retry'}).status_code==404
        assert other.post('/api/v1/commerce/purchases/'+purchase['id']+'/reconcile',json={}).status_code==404
        assert other.post('/api/v1/commerce/demo/offers/change',json={'offer_id':'missing','change':'expired'}).status_code==403


def test_authentication_fail_closed_and_client_owner_rejected(client,monkeypatch):
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/v1/products').status_code==401
    assert client.post('/api/v1/purchases/analyze',json={'text':'Find a laptop under 75000','owner_id':'user-b'}).status_code==422
    from app.core.config import settings
    monkeypatch.setattr(settings,'auth_tokens',{})
    assert client.get('/api/v1/products').status_code==503
