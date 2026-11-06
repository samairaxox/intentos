import json
from pathlib import Path
from decimal import Decimal
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.models.entities import Base
from app.models.commerce import ProductOffer, Merchant
from app.commerce.schemas import CommerceIntent, MerchantOffer
from app.commerce.providers import DemoCatalogProvider, ProviderRegistry
from app.commerce.store import discover_and_persist
from app.commerce.optimizer import optimize_offers
from app.services.catalog import seed


def demo():
    data=Path(__file__).parents[1]/'data'
    raw=json.loads((data/'laptops.json').read_text())+json.loads((data/'accessories.json').read_text())
    provider=DemoCatalogProvider(raw)
    return provider.discover(['laptop','monitor','keyboard','mouse','headphones'])


def test_offer_optimization_landed_costs_and_merchants():
    found=demo()
    intent=CommerceIntent(total_budget=100000,items=[{'category':c,'priority':5 if c=='laptop' else 3} for c in ['laptop','monitor','keyboard','mouse','headphones']])
    result=optimize_offers(intent,found.products,found.offers)
    assert result['status']=='READY' and len(result['combinations'])==3
    combo=result['combinations'][0]
    assert Decimal(combo['total'])<=Decimal('100000')
    assert Decimal(combo['cost_breakdown']['shipping'])>0
    assert sum((Decimal(i['line_total']) for i in combo['items']),Decimal(0))==Decimal(combo['total'])
    assert len(combo['merchant_totals'])>1
    assert all(i['freshness']['label']=='Demo offer' for i in combo['items'])
    assert result['combinations']==optimize_offers(intent,list(reversed(found.products)),list(reversed(found.offers)))['combinations']


def test_shipping_and_verified_discount_control_eligibility():
    found=demo();p=found.products[0]
    base=dict(id='a',product_id=p.id,merchant_id='a',merchant_name='A',base_price='100.00',shipping='20.00',stock=1,source_type='demo',verification_status='demo',retrieved_at=found.offers[0].retrieved_at,provider_id='demo')
    offers=[MerchantOffer(**base),MerchantOffer(**{**base,'id':'b','merchant_id':'b','shipping':'0.00','base_price':'115.00','discounts':[{'label':'unverified','amount':'30.00'}]})]
    intent=CommerceIntent(total_budget=116,items=[{'category':p.category}])
    result=optimize_offers(intent,[p],offers)
    assert result['combinations'][0]['items'][0]['offer']['id']=='b'
    assert result['combinations'][0]['total']=='115.00'
    intent.blocked_merchants=['b']
    assert optimize_offers(intent,[p],offers)['status']=='NO_MATCH'


def test_persisted_offers_preserve_terms_and_merchant_availability():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with sessionmaker(engine,expire_on_commit=False)() as db:
        seed(db);first=discover_and_persist(db,['laptop']);db.commit()
        row=db.get(ProductOffer,first.offers[0].id)
        row.data={**row.data,'base_price':'70000.50'}
        merchant=db.get(Merchant,row.merchant_id);merchant.available=False;db.commit()
        second=discover_and_persist(db,['laptop'])
        offer=next(o for o in second.offers if o.id==row.id)
        assert offer.base_price==Decimal('70000.50') and not offer.merchant_available
    engine.dispose()


def test_zero_quality_scores_do_not_divide_by_zero():
    found=demo()
    products=[p.model_copy(update={'quality_score':0}) for p in found.products]
    intent=CommerceIntent(total_budget=75000,items=[{'category':'laptop'}])
    assert optimize_offers(intent,products,found.offers)['status']=='READY'


def test_quantity_uses_distinct_merchant_stock_not_duplicate_listings():
    found=demo();product=found.products[0]
    raw=dict(id='offer-a',product_id=product.id,merchant_id='merchant-a',merchant_name='A',base_price='100.00',stock=1,source_type='demo',verification_status='demo',retrieved_at=found.offers[0].retrieved_at,provider_id='demo')
    a=MerchantOffer(**raw)
    b=MerchantOffer(**{**raw,'id':'offer-b','merchant_id':'merchant-b','merchant_name':'B'})
    intent=CommerceIntent(total_budget=250,items=[{'category':product.category,'quantity':2}])
    result=optimize_offers(intent,[product],[a,b])
    assert result['combinations'][0]['total']=='200.00'
    duplicate=a.model_copy(update={'id':'same-merchant-other-listing'})
    assert optimize_offers(intent,[product],[a,duplicate])['status']=='NO_MATCH'
