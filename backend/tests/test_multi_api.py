import pytest
from sqlalchemy import select
from app.models.entities import Product, Payment
from app.models.multi_schemas import MultiIntent
from app.api.routes import get_ai
from test_api import client


def intent_payload(budget=100000):
    return {"total_budget":budget,"items":[{"category":c,"priority":5 if c=="laptop" else 3} for c in ["laptop","monitor","keyboard","mouse","headphones"]]}


def plan_cart_order(client, key="bundle-order-key"):
    response=client.post("/api/v1/plans",json={"intent":intent_payload()})
    assert response.status_code==201,response.text
    plan=response.json()
    response=client.post("/api/v1/carts",json={"plan_id":plan["id"]})
    assert response.status_code==201,response.text
    cart=response.json()
    response=client.post("/api/v1/multi/orders",json={"cart_id":cart["id"],"cart_version":cart["version"],"idempotency_key":key})
    assert response.status_code==201,response.text
    return plan,cart,response.json()


def test_multi_gemini_analysis_and_catalog(client):
    class AI:
        def parse_multi(self,text): return MultiIntent.model_validate(intent_payload())
    client.app.dependency_overrides[get_ai]=lambda:AI()
    result=client.post("/api/v1/multi/analyze",json={"text":"Build my coding setup under 100000"})
    assert result.status_code==201,result.text
    assert result.json()["status"]=="READY"
    assert "Await User Selection" in result.json()["workflow"]["steps"]
    assert len(client.get("/api/v1/catalog").json())==46
    assert len(client.get("/api/v1/catalog?category=monitor").json())==6
    assert client.post("/api/v1/optimization",json={"intent":intent_payload()}).json()["status"]=="READY"


def test_multi_checkout_and_idempotency(client):
    plan,cart,order=plan_cart_order(client)
    path="/api/v1/orders/"+order["id"]
    assert client.post(path+"/pay",json={"idempotency_key":"bundle-pay-key"}).status_code==409
    assert order["id"] in client.get("/api/v1/plans/"+plan["id"]).json()["order_ids"]
    details=client.get(path).json()
    assert len(details["items"])==5
    assert sum(i["unit_price"]*i["quantity"] for i in details["items"])==order["amount"]<=100000
    assert client.post(path+"/approve",json={"approved":True}).json()["status"]=="APPROVED"
    response=client.post(path+"/pay",json={"idempotency_key":"bundle-pay-key"})
    assert response.status_code==200,response.text
    assert response.json()["status"]=="PAID"
    assert client.post(path+"/pay",json={"idempotency_key":"bundle-pay-key"}).json()["id"]==response.json()["id"]
    assert client.post(path+"/pay",json={"idempotency_key":"other-pay-key"}).status_code==409
    replay=client.post("/api/v1/multi/orders",json={"cart_id":cart["id"],"cart_version":1,"idempotency_key":"bundle-order-key"})
    assert replay.json()["id"]==order["id"]
    assert client.get(path).json()["payment"]["id"]==response.json()["id"]


@pytest.mark.parametrize("change",["unavailable","price_increase","price_decrease","seller_unavailable"])
def test_catalog_changes_revoke_approval_and_replan(client,change):
    plan,cart,order=plan_cart_order(client)
    path="/api/v1/orders/"+order["id"]
    assert client.post(path+"/approve",json={"approved":True}).status_code==200
    product_id=cart["snapshot"]["items"][0]["product"]["id"]
    assert client.post('/api/v1/plans/'+plan['id']+'/simulate-change',json={'product_id':product_id,'change':change}).status_code==200
    response=client.post(path+"/pay",json={"idempotency_key":"stale-payment-key"})
    assert response.status_code==409,response.text
    revised_id=response.json()["detail"]["revised_plan_id"]
    assert revised_id
    revised=client.get('/api/v1/plans/'+revised_id).json()
    assert revised['revision']==2 and revised['changes']
    assert client.get(path).json()['status']=='CANCELLED'
    assert client.get('/api/v1/carts/'+cart['id']).json()['status']=='STALE'
    with client.factory() as db: assert not list(db.scalars(select(Payment)))
    new_cart=client.post('/api/v1/carts',json={'plan_id':revised_id}).json()
    new_order=client.post('/api/v1/multi/orders',json={'cart_id':new_cart['id'],'cart_version':1,'idempotency_key':'revised-order-key'}).json()
    assert new_order['status']=='PENDING_APPROVAL'
    assert client.post('/api/v1/orders/'+new_order['id']+'/pay',json={'idempotency_key':'revised-payment-key'}).status_code==409


def test_budget_and_preference_replan(client):
    plan,cart,order=plan_cart_order(client)
    updated=intent_payload(80000)
    updated['spending_preference']='savings'
    response=client.post('/api/v1/plans/'+plan['id']+'/replan',json={'intent':updated})
    assert response.status_code==201,response.text
    revised=response.json()
    assert revised['result']['combinations'][0]['total_cost']<=80000
    assert client.get('/api/v1/orders/'+order['id']).json()['status']=='CANCELLED'
    assert client.get('/api/v1/plans/'+plan['id']).json()['status']=='INVALIDATED'


def test_cart_management_and_version_checks(client):
    plan=client.post('/api/v1/plans',json={'intent':intent_payload()}).json()
    alternatives=client.get('/api/v1/plans/'+plan['id']+'/alternatives').json()
    cart=client.post('/api/v1/carts',json={'plan_id':plan['id'],'alternative_index':1}).json()
    ids=[i['product']['id'] for i in alternatives[0]['items'] for _ in range(i['quantity'])]
    updated=client.post('/api/v1/carts/'+cart['id']+'/items',json={'product_ids':ids,'expected_version':1})
    assert updated.status_code==200,updated.text
    assert updated.json()['version']==2
    assert client.post('/api/v1/carts/'+cart['id']+'/items',json={'product_ids':ids,'expected_version':1}).status_code==409
    assert client.post('/api/v1/carts/'+cart['id']+'/items',json={'product_ids':ids[:-1],'expected_version':2}).status_code==422
    assert client.post('/api/v1/multi/orders',json={'cart_id':cart['id'],'cart_version':1,'idempotency_key':'old-version-key'}).status_code==409


def test_multi_payment_failure(client):
    _,_,order=plan_cart_order(client)
    path='/api/v1/orders/'+order['id']
    client.post(path+'/approve',json={'approved':True})
    response=client.post(path+'/pay',json={'idempotency_key':'failed-bundle-key','simulate_failure':True})
    assert response.json()['status']=='PAYMENT_FAILED'
    assert client.get(path).json()['status']=='PAYMENT_FAILED'


def test_missing_and_infeasible_api(client):
    response=client.post('/api/v1/plans',json={'intent':{'items':[]}})
    assert response.json()['status']=='NEEDS_DETAILS'
    impossible=client.post('/api/v1/plans',json={'intent':intent_payload(100)})
    assert impossible.json()['status']=='INFEASIBLE'
    assert client.post('/api/v1/carts',json={'plan_id':impossible.json()['id']}).status_code==422


def test_specification_change_invalidates_approval(client):
    plan,cart,order=plan_cart_order(client)
    path='/api/v1/orders/'+order['id']
    client.post(path+'/approve',json={'approved':True})
    laptop=next(line['product'] for line in cart['snapshot']['items'] if line['product']['category']=='laptop')
    with client.factory() as db:
        row=db.get(Product,laptop['id'])
        row.data={**row.data,'ram_gb':32};db.commit()
    response=client.post(path+'/pay',json={'idempotency_key':'changed-spec-key'})
    assert response.status_code==409
    assert response.json()['detail']['revised_plan_id']
    assert client.get(path).json()['status']=='CANCELLED'
