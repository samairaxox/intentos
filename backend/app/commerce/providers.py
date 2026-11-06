from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from app.commerce.schemas import CanonicalProduct, MerchantOffer, utc
from app.commerce.normalization import ProductNormalizationService, ProductDeduplicationService

@dataclass
class DiscoveryResult:
    products: list[CanonicalProduct]
    offers: list[MerchantOffer]
    warnings: list[str]

class ProductProvider(ABC):
    provider_id: str
    authorized_live: bool = False
    official_documentation: str | None = None

    @abstractmethod
    def discover(self, categories: list[str]) -> DiscoveryResult: ...

class ExternalCommerceProvider(ProductProvider):
    """Contract for authorized integrations. No fabricated live adapter is registered."""
    @abstractmethod
    def revalidate(self, offer_ids: list[str]) -> list[MerchantOffer]: ...

class DemoCatalogProvider(ProductProvider):
    provider_id="demo-catalog"
    merchants=[("demo-alpha","Alpha Demo Supply"),("demo-beta","Beta Demo Electronics"),("demo-gamma","Gamma Demo Store")]

    def __init__(self, products: list[dict], persisted: list[MerchantOffer] | None = None):
        self.products=products
        self.persisted={o.id:o for o in persisted or []}

    def discover(self, categories: list[str]) -> DiscoveryResult:
        products=[];offers=[]
        at=utc()
        for i,raw in enumerate(sorted(self.products,key=lambda p:p["id"])):
            if raw["category"] not in categories: continue
            specs={**raw.get("specifications",{})}
            for key in ["processor_brand","ram_gb","storage_gb","weight_kg","battery_hours","gpu","os"]:
                if key in raw: specs[key]=raw[key]
            products.append(CanonicalProduct(id=raw["id"],category=raw["category"],brand=raw["brand"],model=raw["model"],name=raw["name"],specifications=specs,performance=raw["performance"],quality_score=raw["quality_score"]))
            for slot in range(2):
                merchant_id,name=self.merchants[(i+slot)%3]
                offer_id=f"{raw['id']}:{merchant_id}"
                if offer_id in self.persisted:
                    offers.append(self.persisted[offer_id]);continue
                delta=Decimal("-100.25") if slot else Decimal("0.00")
                base=max(Decimal("1.00"),Decimal(str(raw["price"]))+delta)
                offers.append(MerchantOffer(id=offer_id,product_id=raw["id"],merchant_id=merchant_id,merchant_name=name,
                    base_price=base,shipping=Decimal("149.00") if raw["category"] in ["laptop","monitor"] else Decimal("39.00"),
                    fees=Decimal("10.00"),stock=raw.get("stock",1),available=raw["available"],merchant_available=raw.get("seller_available",True),
                    discounts=[{"label":"Demo confirmed rebate","amount":"20.00","eligibility_verified":True,"eligible":True},
                               {"label":"Unverified promotional possibility (not applied)","amount":"100.00"}],
                    source_type="demo",verification_status="demo",retrieved_at=at,expires_at=at+timedelta(minutes=15),provider_id=self.provider_id))
        return DiscoveryResult(products,offers,[])

class ProviderRegistry:
    def __init__(self): self.providers: dict[str,ProductProvider]={}

    def register(self, provider: ProductProvider):
        if provider.provider_id in self.providers: raise ValueError("Provider ID already registered")
        if provider.authorized_live and not provider.official_documentation:
            raise ValueError("Authorized external providers require official documentation metadata")
        self.providers[provider.provider_id]=provider

    def status(self) -> list[dict]:
        return [{"id":p.provider_id,"mode":"authorized_live" if p.authorized_live else "demo_or_unverified","official_documentation":p.official_documentation} for p in self.providers.values()]

    def discover(self, categories: list[str]) -> DiscoveryResult:
        normalizer=ProductNormalizationService()
        products=[];offers=[];warnings=[]
        for provider in self.providers.values():
            try:
                found=provider.discover(categories)
                normalized_products=[normalizer.product(p.model_dump()) for p in found.products]
                normalized_offers=[normalizer.offer(o.model_dump(),trusted_live=provider.authorized_live) for o in found.offers]
                if any(o.provider_id!=provider.provider_id for o in normalized_offers): raise ValueError("Provider provenance mismatch")
                products.extend(normalized_products);offers.extend(normalized_offers);warnings.extend(found.warnings)
            except Exception:
                warnings.append(f"Provider {provider.provider_id} failed; no unverified result was accepted")
        deduplicated,aliases=ProductDeduplicationService().deduplicate(products)
        unique={}
        for offer in offers:
            if offer.product_id not in aliases:
                warnings.append(f"Offer {offer.id} has no normalized product");continue
            revised=offer.model_copy(update={"product_id":aliases[offer.product_id]})
            key=(revised.provider_id,revised.id)
            if key in unique and unique[key]!=revised: raise ValueError("Conflicting duplicate offer ID")
            unique[key]=revised
        return DiscoveryResult(deduplicated,list(unique.values()),warnings)
