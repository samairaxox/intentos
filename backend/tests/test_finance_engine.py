from decimal import Decimal
import pytest
from pydantic import ValidationError
from test_commerce_workflow import db
from app.commerce.store import discover_and_persist
from app.commerce.schemas import CanonicalProduct,MerchantOffer,utc
from app.finance.schemas import FinancialGoal,ScenarioSpec
from app.finance.engine import evaluate,simulate


def goal(**changes):
    return FinancialGoal.model_validate({'total_budget':'100000.00','mandatory_reserve':'10000.00',
        'items':[{'category':'laptop'},{'category':'monitor'}],**changes})


def test_reserve_category_limits_and_missing_wait_evidence(db):
    found=discover_and_persist(db,['laptop','monitor'])
    result=evaluate(goal(category_limits={'monitor':'20000.00'},patience_days=14),found.products,found.offers,{})
    assert result['reserve']['spendable']=='90000.00'
    assert result['wait']['status']=='INSUFFICIENT_EVIDENCE'
    for strategy in result['strategies']:
        combo=strategy['plan']
        assert combo and Decimal(combo['total'])<=90000
        assert sum(Decimal(l['line_total']) for l in combo['items'] if l['product']['category']=='monitor')<=20000


def test_scenarios_do_not_mutate_markets(db):
    found=discover_and_persist(db,['laptop','monitor'])
    original=[o.model_dump(mode='json') for o in found.offers]
    g=goal()
    changed=simulate(g,found.products,found.offers,{},ScenarioSpec(category_price_change_percent={'laptop':'10'},budget_reduction='15000'))
    assert changed['hypothetical'] and changed['reserve']['spendable']=='75000.00'
    assert all(not s['executable'] for s in changed['strategies'])
    assert original==[o.model_dump(mode='json') for o in found.offers]
    no_laptop=simulate(g,found.products,found.offers,{},ScenarioSpec(unavailable_product_ids=[p.id for p in found.products if p.category=='laptop']))
    assert no_laptop['status']=='NO_MATCH'


def test_cost_and_risk_profiles_materially_differ():
    at=utc()
    product=CanonicalProduct(id='p',category='laptop',brand='Fixture',model='X',name='Fixture',specifications={},performance=80,quality_score=80)
    common=dict(product_id='p',merchant_name='Fixture only',stock=10,retrieved_at=at,provider_id='test-fixture')
    cheap=MerchantOffer(id='cheap',merchant_id='a',base_price='50000',source_type='demo',verification_status='demo',**common)
    verified=MerchantOffer(id='verified',merchant_id='b',base_price='50100',source_type='live_verified',verification_status='verified',**common)
    # These are mocked provenance inputs, not a registered live merchant integration.
    for profile,expected in [('cost_focused','cheap'),('risk_averse','verified')]:
        result=evaluate(goal(items=[{'category':'laptop'}],risk_strategy=profile),[product],[cheap,verified],{},at)
        optimized=next(s for s in result['strategies'] if s['code']=='optimized')
        assert optimized['plan']['items'][0]['offer']['id']==expected
        assert optimized['risk']['offers'][expected]['delivery'] is None


def test_decimal_budget_never_rounds_up_spendable():
    at=utc()
    product=CanonicalProduct(id='p',category='laptop',brand='X',model='X',name='X',specifications={},performance=50,quality_score=50)
    offer=MerchantOffer(id='o',product_id='p',merchant_id='m',merchant_name='M',base_price='90.02',stock=1,source_type='demo',verification_status='demo',retrieved_at=at,provider_id='fixture')
    result=evaluate(goal(total_budget='100.01',mandatory_reserve='10.00',items=[{'category':'laptop'}]),[product],[offer],{},at)
    assert result['status']=='NO_MATCH'
    with pytest.raises(ValidationError): goal(total_budget='100',mandatory_reserve='101')


def test_deadline_and_explicit_essential_staging(db):
    found=discover_and_persist(db,['laptop','headphones'])
    result=evaluate(goal(items=[{'category':'laptop'},{'category':'headphones','required':False}],patience_days=14,deadline=utc().date()),found.products,found.offers,{})
    assert result['wait']['status']=='WAIT_NOT_PERMITTED'
    staged=next(s for s in result['strategies'] if s['code']=='essentials_now')
    assert staged['deferred_categories']==['headphones']
    assert all(l['product']['category']=='laptop' for l in staged['plan']['items'])


def test_exact_hypothetical_price_change_and_conditional_wait():
    at=utc()
    product=CanonicalProduct(id='p',category='laptop',brand='X',model='X',name='Fixture',specifications={},performance=80,quality_score=80)
    offer=MerchantOffer(id='o',product_id='p',merchant_id='m',merchant_name='Fixture',base_price='80.00',shipping='5.00',stock=10,source_type='demo',verification_status='demo',retrieved_at=at,provider_id='fixture')
    g=goal(total_budget='110.00',mandatory_reserve='10.00',items=[{'category':'laptop'}],patience_days=14,opportunity_cost_per_day='0.10',history_mode='synthetic_demo')
    histories={'o':{'evidence':'HISTORICAL_ONLY','minimum':'75.00','volatility_percent':'2.00'}}
    result=evaluate(g,[product],[offer],histories,at)
    assert result['wait']['target_total']=='75.00'
    assert result['wait']['opportunity_cost']=='1.40'
    assert result['wait']['conditional_net_difference']=='8.60'
    assert not result['wait']['executable'] and result['wait']['forecast'] is None
    scenario=simulate(g,[product],[offer],histories,ScenarioSpec(category_price_change_percent={'laptop':'10'}),at)
    assert scenario['strategies'][2]['plan']['total']=='93.00'  # only base price rises; shipping stays 5
    assert offer.base_price==Decimal('80.00')


def test_entire_budget_reserved_and_category_removed(db):
    found=discover_and_persist(db,['laptop','headphones'])
    assert evaluate(goal(mandatory_reserve='100000.00'),found.products,found.offers,{})['status']=='NO_MATCH'
    g=goal(items=[{'category':'laptop'},{'category':'headphones'}])
    result=simulate(g,found.products,found.offers,{},ScenarioSpec(remove_categories=['headphones']))
    assert all(l['product']['category']=='laptop' for l in result['strategies'][2]['plan']['items'])
