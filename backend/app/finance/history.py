"""Landed unit price observations. Synthetic and recorded samples never mix."""
import hashlib
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import select
from app.models.finance import PriceObservation
from app.commerce.pricing import TotalCostService
from app.commerce.schemas import aware, utc


def record(db, offer, *, synthetic_day=None, factor=Decimal(1)):
    kind = 'synthetic' if synthetic_day is not None else ('recorded_live' if offer.source_type == 'live_verified' else 'recorded_demo')
    price = (Decimal(TotalCostService().calculate(offer)['final_price']) * factor).quantize(Decimal('.01'))
    # Re-reading the same quote must not manufacture independent market observations.
    key = hashlib.sha256(f'{kind}:{offer.id}:{synthetic_day if synthetic_day is not None else offer.retrieved_at.isoformat()}:{price}'.encode()).hexdigest()
    if db.scalar(select(PriceObservation.id).where(PriceObservation.quote_key == key)):
        return False
    db.add(PriceObservation(quote_key=key, product_id=offer.product_id, merchant_id=offer.merchant_id,
        offer_id=offer.id, price=price, currency=offer.currency,
        observed_at=utc()-timedelta(days=synthetic_day) if synthetic_day is not None else utc(),
        source='synthetic_fixture_v1' if synthetic_day is not None else offer.source_type,
        verification='synthetic_unverified' if synthetic_day is not None else offer.verification_status, kind=kind))
    db.flush()
    return True


def seed_synthetic(db, offers):
    count = 0
    factors = ['1.04','1.02','1.03','.98','1.01','1.00','.97','1.02','1.01','.99','1.00','1.03','1.01','1.00']
    for offer in offers:
        for index, factor in enumerate(factors):
            count += record(db, offer, synthetic_day=14-index, factor=Decimal(factor))
    return count


def history(db, offer_id, mode='recorded', at=None):
    at = aware(at or utc())
    query = select(PriceObservation).where(PriceObservation.offer_id == offer_id,
        PriceObservation.observed_at >= at-timedelta(days=90), PriceObservation.observed_at <= at)
    query = query.where(PriceObservation.kind == 'synthetic') if mode == 'synthetic_demo' else query.where(PriceObservation.kind != 'synthetic')
    rows = list(db.scalars(query.order_by(PriceObservation.observed_at, PriceObservation.id)))
    values = [r.price for r in rows]
    points = [{'price':format(r.price,'.2f'),'at':aware(r.observed_at).isoformat(),'source':r.source,'verification':r.verification,'kind':r.kind} for r in rows]
    result = {'offer_id':offer_id,'mode':mode,'price_kind':'landed_unit','currency':'INR','points':points,'count':len(rows),
        'evidence':'INSUFFICIENT_EVIDENCE','forecast':None,'assumption':'Observed history is not a prediction of future prices.'}
    if not values:
        return result
    mean = sum(values)/len(values)
    deviation = (sum((v-mean)**2 for v in values)/len(values)).sqrt()
    span = (aware(rows[-1].observed_at)-aware(rows[0].observed_at)).total_seconds()/86400
    distinct = len({aware(r.observed_at).date() for r in rows})
    result.update(minimum=format(min(values),'.2f'), maximum=format(max(values),'.2f'), average=format(mean,'.2f'),
        standard_deviation=format(deviation,'.2f'), volatility_percent=format(deviation/mean*100 if mean else Decimal(0),'.2f'),
        recent_change=format(values[-1]-values[-2],'.2f') if len(values)>1 else None,
        distinct_days=distinct, span_days=round(span,3),
        evidence='HISTORICAL_ONLY' if len(values)>=8 and distinct>=7 and span>=7 else 'INSUFFICIENT_EVIDENCE')
    low, high = min(values), max(values)
    result['chart_points'] = [{'x':str(10+Decimal(i)*280/max(1,len(values)-1)),
        'y':str(90-(v-low)*80/(high-low)) if high>low else '50'} for i,v in enumerate(values)]
    return result
