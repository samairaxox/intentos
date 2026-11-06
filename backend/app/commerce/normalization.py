import hashlib
import json
import unicodedata
from app.commerce.schemas import CanonicalProduct, MerchantOffer

class ProductNormalizationService:
    def product(self, raw: dict) -> CanonicalProduct:
        return CanonicalProduct.model_validate(raw)

    def offer(self, raw: dict, *, trusted_live: bool = False) -> MerchantOffer:
        offer=MerchantOffer.model_validate(raw)
        if offer.source_type=="live_verified" and not trusted_live:
            raise ValueError("Only an authorized registered provider may assert verified live provenance")
        return offer

class ProductDeduplicationService:
    def identity(self, product: CanonicalProduct) -> str:
        normalized=lambda s:" ".join(unicodedata.normalize("NFKC",s).casefold().split())
        # Specifications remain part of identity: different RAM/storage variants are never fuzzy-merged.
        identity=[normalized(product.category),normalized(product.brand),normalized(product.model),product.specifications]
        return hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(",",":")).encode()).hexdigest()

    def deduplicate(self, products: list[CanonicalProduct]) -> tuple[list[CanonicalProduct],dict[str,str]]:
        unique={};aliases={}
        for product in sorted(products,key=lambda p:p.id):
            fingerprint=self.identity(product)
            unique.setdefault(fingerprint,product)
            aliases[product.id]=unique[fingerprint].id
        return list(unique.values()),aliases
