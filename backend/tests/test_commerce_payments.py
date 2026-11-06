from datetime import timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.commerce.ai import CommerceAI
from app.commerce.schemas import SessionStart,CommerceIntent,PurchaseCreate,ExecuteRequest,RetryRequest
from app.commerce.sessions import create_session
from app.commerce.checkout import create_purchase,present_purchase,resolve_demo_outcome
from app.commerce.payments import PaymentAuthorizationService,PaymentExecutionService,PaymentReconciliationService,suborders,intent_for,attempts_for
from app.commerce.payment_providers import MockPaymentProvider
from app.models.commerce import PaymentAttempt,MockProviderReceipt,ProductOffer
from test_commerce_workflow import db

@pytest.fixture
def purchase(db):
    _,plan=create_session(db,SessionStart(intent=CommerceIntent(total_budget=100000,items=[{'category':c} for c in ['laptop','monitor','keyboard','mouse','headphones']])),CommerceAI())
    purchase=create_purchase(db,PurchaseCreate(plan_id=plan.id,idempotency_key='purchase-key-001'),CommerceAI())
    assert len(suborders(db,purchase))>=2
    return purchase


def approve(db,purchase):return PaymentAuthorizationService().approve(db,purchase.id,CommerceAI())


def test_approval_and_idempotent_complete_payment(db,purchase):
    request=ExecuteRequest(idempotency_key='execute-key-001')
    with pytest.raises(HTTPException):PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    approve(db,purchase)
    result=PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    assert result.status=='PAID'
    count=len(list(db.scalars(select(PaymentAttempt))))
    PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    assert len(list(db.scalars(select(PaymentAttempt))))==count
    assert all(s['status']=='CAPTURED' for s in present_purchase(db,purchase)['suborders'])


def test_partial_failure_and_mock_compensation(db,purchase):
    approve(db,purchase)
    failing=suborders(db,purchase)[1].merchant_id
    request=ExecuteRequest(idempotency_key='execute-partial-001',simulations={failing:'failure'})
    PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    assert purchase.status=='PARTIAL_FAILURE'
    assert Decimal(present_purchase(db,purchase)['captured_total'])>0
    PaymentReconciliationService().compensate(db,purchase.id,pending=True)
    assert purchase.status=='COMPENSATION_PENDING'
    assert Decimal(present_purchase(db,purchase)['captured_total'])>0
    assert present_purchase(db,purchase)['refunded_total']=='0.00'
    PaymentReconciliationService().compensate(db,purchase.id)
    assert purchase.status=='COMPENSATED'
    assert present_purchase(db,purchase)['captured_total']=='0.00'
    count=len(list(db.scalars(select(MockProviderReceipt))))
    PaymentReconciliationService().compensate(db,purchase.id)
    assert len(list(db.scalars(select(MockProviderReceipt))))==count


def test_timeout_captured_reconciles_before_resume(db,purchase):
    approve(db,purchase)
    first=suborders(db,purchase)[0].merchant_id
    request=ExecuteRequest(idempotency_key='execute-timeout-001',simulations={first:'timeout_captured'})
    PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    assert purchase.status=='PAYMENT_UNKNOWN'
    assert len(list(db.scalars(select(MockProviderReceipt))))==1
    PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    assert len(list(db.scalars(select(MockProviderReceipt))))==1
    PaymentReconciliationService().reconcile(db,purchase.id)
    PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    assert purchase.status=='PAID'
    assert len(list(db.scalars(select(PaymentAttempt))))==len(suborders(db,purchase))


def test_unknown_cannot_retry_or_refund_until_resolved(db,purchase,monkeypatch):
    monkeypatch.setattr(PaymentExecutionService,'retry_delay',timedelta(0))
    approve(db,purchase)
    first=suborders(db,purchase)[0]
    request=ExecuteRequest(idempotency_key='execute-unknown-001',simulations={first.merchant_id:'timeout_unknown'})
    PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    PaymentReconciliationService().reconcile(db,purchase.id)
    assert purchase.status=='PAYMENT_UNKNOWN'
    with pytest.raises(HTTPException):PaymentExecutionService().retry(db,first.id,RetryRequest(idempotency_key='unknown-retry-key'),CommerceAI())
    with pytest.raises(HTTPException):PaymentReconciliationService().compensate(db,purchase.id)
    payment=intent_for(db,first);attempt=attempts_for(db,payment)[-1]
    resolve_demo_outcome(db,attempt.id,'FAILED')
    PaymentReconciliationService().reconcile(db,purchase.id)
    PaymentExecutionService().retry(db,first.id,RetryRequest(idempotency_key='confirmed-retry-key'),CommerceAI())
    PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    assert purchase.status=='PAID'


def test_price_change_after_approval_cancels_before_charge(db,purchase):
    approve(db,purchase)
    row=db.get(ProductOffer,purchase.snapshot['items'][0]['offer']['id'])
    row.data={**row.data,'base_price':format(Decimal(row.data['base_price'])+Decimal('4000.00'),'.2f')};db.commit()
    with pytest.raises(HTTPException) as error:PaymentExecutionService().execute(db,purchase.id,ExecuteRequest(idempotency_key='stale-execution-key'),CommerceAI())
    assert error.value.detail['revised_plan_id']
    assert purchase.status=='APPROVAL_INVALIDATED'
    assert not list(db.scalars(select(MockProviderReceipt)))


def test_retry_bound_and_idempotency(db,purchase,monkeypatch):
    monkeypatch.setattr(PaymentExecutionService,'retry_delay',timedelta(0))
    approve(db,purchase);first=suborders(db,purchase)[0]
    modes={s.merchant_id:'failure' for s in suborders(db,purchase)}
    PaymentExecutionService().execute(db,purchase.id,ExecuteRequest(idempotency_key='all-fail-execution',simulations=modes),CommerceAI())
    for n in range(2):PaymentExecutionService().retry(db,first.id,RetryRequest(idempotency_key=f'retry-failure-{n}',simulation='failure'),CommerceAI())
    with pytest.raises(HTTPException):PaymentExecutionService().retry(db,first.id,RetryRequest(idempotency_key='retry-failure-overlimit'),CommerceAI())
    assert purchase.status=='PAYMENT_FAILED'
    assert len(attempts_for(db,intent_for(db,first)))==3


def test_reconciliation_fences_late_worker(db,purchase,monkeypatch):
    approve(db,purchase)
    original=MockPaymentProvider.execute
    interrupted={'done':False}
    def provider(self,**kwargs):
        outcome=original(self,**kwargs)
        if not interrupted['done']:
            interrupted['done']=True
            PaymentReconciliationService().reconcile(db,purchase.id)
        return outcome
    monkeypatch.setattr(MockPaymentProvider,'execute',provider)
    request=ExecuteRequest(idempotency_key='fenced-execution-key')
    PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    assert len(list(db.scalars(select(MockProviderReceipt))))==1
    PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    assert purchase.status=='PAID'
    assert len(list(db.scalars(select(MockProviderReceipt))))==len(suborders(db,purchase))


def test_reconciliation_rejects_wrong_provider_amount(db,purchase):
    approve(db,purchase)
    first=suborders(db,purchase)[0]
    request=ExecuteRequest(idempotency_key='mismatched-amount-execution',simulations={first.merchant_id:'timeout_captured'})
    PaymentExecutionService().execute(db,purchase.id,request,CommerceAI())
    receipt=db.scalars(select(MockProviderReceipt)).first()
    receipt.amount+=Decimal('0.01');db.commit()
    PaymentReconciliationService().reconcile(db,purchase.id)
    assert purchase.status=='PAYMENT_UNKNOWN' and first.status=='UNKNOWN'
