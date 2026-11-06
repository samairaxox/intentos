from decimal import Decimal
from app.commerce.schemas import MerchantOffer, aware, utc

class TotalCostService:
    def calculate(self, offer: MerchantOffer, at=None) -> dict:
        at=at or utc()
        confirmed=[];potential=[]
        for discount in offer.discounts:
            active=discount.expires_at is None or aware(discount.expires_at)>aware(at)
            if discount.eligibility_verified and discount.eligible and active:
                confirmed.append(discount)
            else: potential.append(discount)
        deduction=min(offer.base_price,sum((d.amount for d in confirmed),Decimal("0.00")))
        taxes=offer.estimated_taxes if offer.taxes_supported else Decimal("0.00")
        total=offer.base_price-deduction+offer.shipping+offer.fees+taxes
        return {"base_price":format(offer.base_price,".2f"),"confirmed_discount":format(deduction,".2f"),
                "confirmed_discounts":[d.model_dump(mode="json") for d in confirmed],
                "potential_discounts":[d.model_dump(mode="json") for d in potential],
                "shipping":format(offer.shipping,".2f"),"fees":format(offer.fees,".2f"),"estimated_taxes":format(taxes,".2f"),
                "taxes_supported":offer.taxes_supported,"final_price":format(total,".2f"),"final_minor":int(total*100),
                "cost_scope":"Per-unit shipping and fees; taxes included only when explicitly supported. No assumed basket thresholds."}
