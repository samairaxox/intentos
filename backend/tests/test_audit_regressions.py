"""Independent audit probes. Strict xfails preserve unresolved findings without changing production code."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.main import app
from app.db.session import get_db
from app.models.entities import Product, Payment
from test_api import client, make_order
from app.models.schemas import Intent, Constraint
from app.services.optimization import eligible
from app.services.catalog import LocalCatalogProvider


def test_approved_single_order_rejects_changed_seller(client):
    order,_=make_order(client,'audit-seller-order')
    path='/api/v1/orders/'+order['id']
    assert client.post(path+'/approve',json={'approved':True}).status_code==200
    with client.factory() as db:
        product=db.get(Product,order['product_id'])
        product.data={**product.data,'seller':'Changed merchant after approval'};db.commit()
    response=client.post(path+'/pay',json={'idempotency_key':'audit-changed-seller-pay'})
    assert response.status_code==409, f'Expected reapproval; observed {response.status_code}: {response.text}'


def test_cross_phase_session_read_is_a_client_error(client):
    result=client.post('/api/v1/commerce/sessions',json={'intent':{'total_budget':75000,'items':[{'category':'laptop'}]}})
    assert result.status_code==201
    with TestClient(app,raise_server_exceptions=False,headers=client.headers) as transport:
        response=transport.get('/api/v1/purchases/'+result.json()['session']['id'])
    assert response.status_code in [404,422], f'Observed {response.status_code}: {response.text}'


def test_database_outage_has_controlled_service_response(client,tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path / 'missing-directory' / 'unavailable.db'}")
    def broken_database():
        with Session(engine) as db:yield db
    previous=app.dependency_overrides[get_db]
    app.dependency_overrides[get_db]=broken_database
    try:
        with TestClient(app,raise_server_exceptions=False,headers=client.headers) as transport:
            response=transport.get('/api/v1/products')
        assert response.status_code==503, f'Observed {response.status_code}: {response.text}'
    finally:
        app.dependency_overrides[get_db]=previous
        engine.dispose()


def test_requested_phase1_hard_and_soft_requirements(client):
    intent=Intent(category='laptop',max_budget=75000,use_case='coding and AI development',
        required_specifications=[Constraint(field='processor_brand',operator='eq',value='Intel'),Constraint(field='ram_gb',operator='min',value=16)],
        soft_preferences=[Constraint(field='weight_kg',operator='max',value=1.4),Constraint(field='battery_hours',operator='min',value=10)])
    with client.factory() as db:
        products=LocalCatalogProvider(db).discover(['laptop'])
    accepted=[p for p in products if eligible(p,intent)]
    assert accepted and all(p['price']<=75000 and p['processor_brand']=='Intel' and p['ram_gb']>=16 for p in accepted)
    assert any(p['weight_kg']>1.4 for p in accepted)  # preference does not become a mandatory cutoff
    impossible=intent.model_copy(update={'max_budget':1})
    assert not any(eligible(p,impossible) for p in products)
    conflicting=intent.model_copy(update={'hard_constraints':[Constraint(field='ram_gb',operator='max',value=8)]})
    assert not any(eligible(p,conflicting) for p in products)


def test_anonymous_access_is_denied(client):
    order,_=make_order(client,'audit-anonymous-order')
    # Anonymous callers must not read or authorize a known purchase.
    with TestClient(app) as anonymous:
        response=anonymous.get('/api/v1/orders/'+order['id'])
        approved=anonymous.post('/api/v1/orders/'+order['id']+'/approve',json={'approved':True})
    assert response.status_code==401 and approved.status_code==401


def test_invalid_single_order_transitions_and_amount_input(client):
    order,_=make_order(client,'audit-transitions-order')
    path='/api/v1/orders/'+order['id']
    assert client.post(path+'/pay',json={'idempotency_key':'audit-before-approval'}).status_code==409
    assert client.post(path+'/approve',json={'approved':True,'amount':1}).status_code==422
    assert client.post(path+'/cancel').status_code==200
    assert client.post(path+'/approve',json={'approved':True}).status_code==409
    assert client.post(path+'/pay',json={'idempotency_key':'audit-after-cancel'}).status_code==409
    with client.factory() as db: assert not list(db.scalars(select(Payment)))


def test_sql_like_identifier_is_not_interpreted_as_a_query(client):
    order,_=make_order(client,'audit-query-probe')
    response=client.get("/api/v1/orders/'%20OR%201=1--")
    assert response.status_code==404
    assert client.get('/api/v1/orders/'+order['id']).status_code==200
