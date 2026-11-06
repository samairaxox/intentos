from test_api import client
from app.api.routes import get_ai
from app.models.schemas import Intent
from app.models.multi_schemas import MultiIntent
from app.models.entities import Product,Payment
from sqlalchemy import select
from app.services.gemini import AIUnavailable


def test_single_resume_preserves_parse_but_rediscovers_changed_catalog(client):
    class AI:
        parses=0;failed=False
        def parse(self,text):self.parses+=1;return Intent(category='laptop',max_budget=75000)
        def explain(self,rows):
            if not self.failed:self.failed=True;raise AIUnavailable('fixture outage')
            return {r['product']['id']:'Fixture grounded explanation' for r in rows}
    ai=AI();client.app.dependency_overrides[get_ai]=lambda:ai
    response=client.post('/api/v1/purchases/analyze',json={'text':'Laptop under 75000 for coding'})
    assert response.status_code==503
    sid=response.json()['detail']['session_id']
    partial=client.get('/api/v1/purchases/'+sid).json()
    assert partial['status']=='INTERRUPTED' and partial['recommendations']
    removed=partial['recommendations'][0]['product']['id']
    assert client.post('/api/v1/orders',json={'session_id':sid,'product_id':removed,'idempotency_key':'incomplete-workflow-order'}).status_code==409
    with client.factory() as db:
        product=db.get(Product,removed);product.data={**product.data,'available':False};db.commit()
    resumed=client.post('/api/v1/purchases/'+sid+'/resume').json()
    assert resumed['status']=='READY' and ai.parses==1
    assert removed not in [r['product']['id'] for r in resumed['recommendations']]
    assert client.post('/api/v1/purchases/'+sid+'/resume').json()==resumed
    with client.factory() as db:assert not list(db.scalars(select(Payment)))


def test_multi_resume_after_discovery_failure_keeps_interpretation(client,monkeypatch):
    from app.services.catalog import LocalCatalogProvider
    class AI:
        parses=0
        def parse_multi(self,text):
            self.parses+=1;return MultiIntent(total_budget=100000,items=[{'category':'laptop'},{'category':'monitor'}])
    ai=AI();client.app.dependency_overrides[get_ai]=lambda:ai
    original=LocalCatalogProvider.discover
    def fail(self,categories=None):raise RuntimeError('private fixture details must not reach clients')
    monkeypatch.setattr(LocalCatalogProvider,'discover',fail)
    response=client.post('/api/v1/multi/analyze',json={'text':'Laptop and monitor under 100000'})
    assert response.status_code==503 and 'private fixture' not in response.text
    pid=response.json()['detail']['plan_id']
    assert client.get('/api/v1/plans/'+pid).json()['status']=='INTERRUPTED'
    monkeypatch.setattr(LocalCatalogProvider,'discover',original)
    resumed=client.post('/api/v1/plans/'+pid+'/resume').json()
    assert resumed['status']=='READY' and ai.parses==1
    assert client.post('/api/v1/plans/'+pid+'/resume').json()['id']==pid
