from datetime import timedelta
from app.commerce.schemas import MerchantOffer, aware, utc

class OfferFreshnessService:
    max_age=timedelta(minutes=15)

    def inspect(self, offer: MerchantOffer, at=None) -> dict:
        at=aware(at or utc())
        retrieved=aware(offer.retrieved_at)
        deadline=min(retrieved+self.max_age,aware(offer.expires_at)) if offer.expires_at else retrieved+self.max_age
        fresh=retrieved<=at<deadline
        eligible=fresh and offer.available and offer.merchant_available and offer.stock>0 and offer.source_type in ["demo","live_verified"]
        reason="current" if eligible else "stale_or_expired" if not fresh else "unverified_or_cached" if offer.source_type not in ["demo","live_verified"] else "unavailable"
        return {"fresh":fresh,"checkout_eligible":eligible,"reason":reason,"valid_until":deadline.isoformat(),
                "label":"Demo offer" if offer.source_type=="demo" else "Verified live offer" if offer.source_type=="live_verified" and fresh else "Cached offer" if offer.source_type=="cached" else "Unverified external information"}
