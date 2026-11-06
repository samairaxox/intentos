from datetime import timedelta
from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.commerce.schemas import MerchantOffer, CanonicalProduct, Discount, utc
from app.commerce.pricing import TotalCostService
from app.commerce.freshness import OfferFreshnessService
from app.commerce.normalization import ProductDeduplicationService, ProductNormalizationService
from app.commerce.providers import ProviderRegistry, ProductProvider, DiscoveryResult

@pytest.fixture
def offer():
    return MerchantOffer(id="o1",product_id="p1",merchant_id="m1",merchant_name="Demo seller",base_price="100.10",shipping="10.20",fees="1.05",stock=3,source_type="demo",verification_status="demo",retrieved_at=utc(),provider_id="demo")

def test_decimal_totals_and_discount_eligibility(offer):
    offer.discounts=[Discount(label="verified",amount="5.05",eligibility_verified=True,eligible=True)]
    offer=MerchantOffer.model_validate(offer.model_dump())
    offer.discounts.append(Discount(label='potential',amount='99.00'))
    priced=TotalCostService().calculate(offer)
    assert priced['final_price']=='106.30' and priced['final_minor']==10630
    assert priced['confirmed_discount']=='5.05' and len(priced['potential_discounts'])==1

@pytest.mark.parametrize('invalid',[0.1,'NaN','Infinity','-1.00','1.001',True])
def test_money_rejects_float_invalid_or_fractional_paise(offer,invalid):
    with pytest.raises((ValidationError,ValueError)):
        MerchantOffer.model_validate({**offer.model_dump(),'base_price':invalid})

def test_freshness_expiry_and_source_labels(offer):
    freshness=OfferFreshnessService()
    assert freshness.inspect(offer)['checkout_eligible']
    assert not freshness.inspect(offer,utc()+timedelta(minutes=16))['checkout_eligible']
    for source in ['cached','unverified']:
        changed=offer.model_copy(update={'source_type':source,'verification_status':'unverified'})
        assert not freshness.inspect(changed)['checkout_eligible']
    assert not freshness.inspect(offer.model_copy(update={'expires_at':utc()-timedelta(seconds=1)}))['fresh']

def test_normalization_rejects_forged_live_provenance(offer):
    raw={**offer.model_dump(),'source_type':'live_verified','verification_status':'verified'}
    with pytest.raises(ValueError,match='authorized'):
        ProductNormalizationService().offer(raw)
    assert ProductNormalizationService().offer(raw,trusted_live=True).source_type=='live_verified'

def test_deduplication_keeps_different_configurations():
    raw=dict(id='a',category='laptop',brand='Lenovo',model=' Model X ',name='Sample',specifications={'ram_gb':16},performance=70,quality_score=70)
    products=[CanonicalProduct(**raw),CanonicalProduct(**{**raw,'id':'b','brand':' lenovo ','model':'model x'}),CanonicalProduct(**{**raw,'id':'c','specifications':{'ram_gb':32}})]
    unique,aliases=ProductDeduplicationService().deduplicate(products)
    assert len(unique)==2 and aliases['b']=='a' and aliases['c']=='c'

def test_registry_isolates_provider_failure():
    class Broken(ProductProvider):
        provider_id='broken'
        def discover(self,categories): raise RuntimeError('provider unavailable')
    registry=ProviderRegistry();registry.register(Broken())
    result=registry.discover(['laptop'])
    assert not result.offers and result.warnings
