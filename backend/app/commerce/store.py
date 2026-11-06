from sqlalchemy import select
from app.models.entities import Product
from app.models.commerce import Merchant, ProductOffer
from app.commerce.providers import ProviderRegistry, DemoCatalogProvider
from app.commerce.schemas import MerchantOffer


def registry_for(db) -> ProviderRegistry:
    products=[p.data for p in db.scalars(select(Product))]
    persisted=[]
    for row in db.scalars(select(ProductOffer).where(ProductOffer.data.is_not(None))):
        offer=MerchantOffer.model_validate(row.data)
        merchant=db.get(Merchant,row.merchant_id)
        product=db.get(Product,row.product_id)
        offer=offer.model_copy(update={"merchant_available":bool(merchant and merchant.available),
            "available":offer.available and bool(product and product.data.get("available")),
            "stock":min(offer.stock,product.data.get("stock",0)) if product else 0})
        persisted.append(offer)
    registry=ProviderRegistry()
    registry.register(DemoCatalogProvider(products,persisted))
    return registry


def discover_and_persist(db,categories):
    result=registry_for(db).discover(categories)
    for offer in result.offers:
        if not db.get(Merchant,offer.merchant_id):
            db.add(Merchant(id=offer.merchant_id,name=offer.merchant_name,available=offer.merchant_available,source_type=offer.source_type))
    db.flush()
    for offer in result.offers:
        if not db.get(ProductOffer,offer.id):
            db.add(ProductOffer(id=offer.id,product_id=offer.product_id,merchant_id=offer.merchant_id,data=offer.model_dump(mode="json")))
    db.flush()
    from app.finance.history import record
    for offer in result.offers: record(db,offer)
    return result


def current_offer(db,offer_id):
    row=db.get(ProductOffer,offer_id)
    if not row:return None
    offer=MerchantOffer.model_validate(row.data)
    merchant=db.get(Merchant,row.merchant_id)
    product=db.get(Product,row.product_id)
    return offer.model_copy(update={"merchant_available":bool(merchant and merchant.available),
        "available":offer.available and bool(product and product.data.get("available")),
        "stock":min(offer.stock,product.data.get("stock",0)) if product else 0})
