from decimal import Decimal
from sqlalchemy import select
from test_commerce_workflow import db
from app.commerce.store import discover_and_persist
from app.finance.history import history, seed_synthetic, record
from app.models.finance import PriceObservation


def test_recorded_history_is_idempotent_and_not_a_forecast(db):
    offer=discover_and_persist(db,['laptop']).offers[0]
    assert not record(db,offer)
    result=history(db,offer.id)
    assert result['count']==1 and result['evidence']=='INSUFFICIENT_EVIDENCE'
    assert result['forecast'] is None
    assert result['points'][0]['kind']=='recorded_demo'


def test_synthetic_history_separate_and_reproducible(db):
    offer=discover_and_persist(db,['laptop']).offers[0]
    assert seed_synthetic(db,[offer])==14
    assert seed_synthetic(db,[offer])==0
    assert history(db,offer.id)['count']==1
    result=history(db,offer.id,'synthetic_demo')
    assert result['count']==14 and result['evidence']=='HISTORICAL_ONLY'
    rows=list(db.scalars(select(PriceObservation).where(PriceObservation.kind=='synthetic',PriceObservation.offer_id==offer.id)))
    mean=sum(r.price for r in rows)/len(rows)
    assert result['average']==format(mean,'.2f')
    assert result['minimum']==format(min(r.price for r in rows),'.2f')
    assert Decimal(result['volatility_percent'])>0
    assert all(p['verification']=='synthetic_unverified' for p in result['points'])
