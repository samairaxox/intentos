import hashlib
import json
from uuid import uuid4
from datetime import timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select,update
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.models.commerce import (CommercePurchase,MerchantSuborder,PaymentIntentRecord,PaymentAttempt,ReconciliationRecord,MockProviderReceipt,CommercePlan)
from app.commerce.schemas import utc,aware
from app.commerce.payment_providers import MockPaymentProvider
from app.commerce.tracing import TraceRecorder
from app.commerce import sessions


def digest(snapshot):return hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def purchase_for(db,purchase_id):
    row=db.get(CommercePurchase,purchase_id)
    if not row:raise HTTPException(404,'Commerce purchase not found')
    plan=db.get(CommercePlan,row.plan_id)
    sessions.session_for(db,plan.session_id)
    db.refresh(row)
    return row,plan


def suborders(db,purchase):return list(db.scalars(select(MerchantSuborder).where(MerchantSuborder.purchase_id==purchase.id).order_by(MerchantSuborder.merchant_id).execution_options(populate_existing=True)))
def intent_for(db,sub):return db.scalar(select(PaymentIntentRecord).where(PaymentIntentRecord.suborder_id==sub.id))
def attempts_for(db,intent):return list(db.scalars(select(PaymentAttempt).where(PaymentAttempt.intent_id==intent.id).order_by(PaymentAttempt.attempt_number)))


def aggregate(db,purchase):
    states=[s.status for s in suborders(db,purchase)]
    if purchase.execution_token and not any(s in ['UNKNOWN','PROCESSING'] for s in states):
        purchase.status='EXECUTING';return purchase.status
    if any(s in ['UNKNOWN','PROCESSING'] for s in states):purchase.status='PAYMENT_UNKNOWN'
    elif states and all(s=='CAPTURED' for s in states):purchase.status='PAID'
    elif 'REFUND_PENDING' in states:purchase.status='COMPENSATION_PENDING'
    elif 'REFUNDED' in states and all(s in ['REFUNDED','FAILED','CHECKOUT_FAILED','CANCELLED'] for s in states):purchase.status='COMPENSATED'
    elif 'CAPTURED' in states:purchase.status='PARTIAL_FAILURE'
    elif states and all(s in ['FAILED','CHECKOUT_FAILED','CANCELLED'] for s in states):purchase.status='PAYMENT_FAILED'
    elif any(s in ['FAILED','CHECKOUT_FAILED'] for s in states):purchase.status='PARTIAL_FAILURE'
    elif states and all(s=='AUTHORIZED' for s in states):purchase.status='APPROVED'
    action={'PAYMENT_UNKNOWN':'RECONCILE_WITH_PROVIDER_BEFORE_RETRY','PARTIAL_FAILURE':'REVIEW_PARTIAL_OUTCOME_OR_EXPLICITLY_RETRY_CONFIRMED_FAILURE','COMPENSATION_PENDING':'AWAIT_COMPENSATION_CONFIRMATION','PAYMENT_FAILED':'EXPLICIT_RETRY_OR_NEW_APPROVAL_REQUIRED'}.get(purchase.status)
    purchase.workflow={**(purchase.workflow or {}),'status':purchase.status,'action_required':action}
    return purchase.status


class PaymentIntentService:
    def create(self,db,purchase):
        for sub in suborders(db,purchase):
            if not intent_for(db,sub):db.add(PaymentIntentRecord(suborder_id=sub.id,amount=sub.amount,status='REQUIRES_APPROVAL'))
        db.flush()


class PaymentAuthorizationService:
    def approve(self,db,purchase_id,ai):
        purchase,plan=purchase_for(db,purchase_id)
        if purchase.status=='APPROVED':
            sessions.ensure_current(db,plan,purchase.snapshot,ai)
            return purchase
        if purchase.status!='PENDING_APPROVAL':raise HTTPException(409,'Purchase cannot be approved in its current state')
        sessions.ensure_current(db,plan,purchase.snapshot,ai)
        self.verify_amounts(db,purchase)
        purchase.approved_at=utc();purchase.authorization_digest=digest(purchase.snapshot);purchase.status='APPROVED'
        for sub in suborders(db,purchase):sub.status='AUTHORIZED';intent_for(db,sub).status='AUTHORIZED'
        TraceRecorder(db,plan.id,plan.session_id).record('approval','APPROVED',{'purchase_id':purchase.id})
        db.commit();return purchase

    def verify_amounts(self,db,purchase):
        from app.finance.service import policy_check
        policy_check(db,db.get(CommercePlan,purchase.plan_id),purchase.snapshot,purchase_id=purchase.id,exposure=True)
        if sum((s.amount for s in suborders(db,purchase)),Decimal('0.00'))!=purchase.amount or purchase.amount!=Decimal(purchase.snapshot['total']):raise HTTPException(409,'Server-side parent amount mismatch')
        for sub in suborders(db,purchase):
            intent=intent_for(db,sub)
            expected=sum((Decimal(line['line_total']) for line in sub.items),Decimal('0.00'))
            if expected!=sub.amount or not intent or intent.amount!=sub.amount or intent.currency!='INR':raise HTTPException(409,'Server-side merchant amount mismatch')

    def verify(self,db,purchase):
        if not purchase.approved_at or purchase.authorization_digest!=digest(purchase.snapshot):raise HTTPException(409,'Explicit authorization for these exact terms is required')
        self.verify_amounts(db,purchase)


class PaymentExecutionService:
    retry_delay=timedelta(seconds=2)
    max_attempts=3

    def acquire(self,db,purchase):
        token=str(uuid4())
        changed=db.execute(update(CommercePurchase).where(CommercePurchase.id==purchase.id,CommercePurchase.execution_token.is_(None)).values(execution_token=token,status="EXECUTING"))
        if changed.rowcount!=1:
            db.rollback();raise HTTPException(409,'An execution is active or interrupted; reconcile before resuming')
        db.commit();return token

    def owns(self,db,purchase,token):
        return db.scalar(select(CommercePurchase.execution_token).where(CommercePurchase.id==purchase.id))==token

    def release(self,db,purchase,token):
        db.execute(update(CommercePurchase).where(CommercePurchase.id==purchase.id,CommercePurchase.execution_token==token).values(execution_token=None))
        db.commit();db.refresh(purchase)

    def execute_suborder(self,db,purchase,plan,sub,key,simulation,*,retry=False,lease=None):
        if lease and not self.owns(db,purchase,lease):return None
        payment=intent_for(db,sub);prior=attempts_for(db,payment)
        existing=db.scalar(select(PaymentAttempt).where(PaymentAttempt.idempotency_key==key))
        if existing:
            if existing.intent_id!=payment.id or existing.simulation!=simulation:raise HTTPException(409,'Payment idempotency key reused with different inputs')
            return existing
        if sub.status in ['CAPTURED','REFUNDED','REFUND_PENDING']:return prior[-1] if prior else None
        if sub.status in ['UNKNOWN','PROCESSING']:raise HTTPException(409,'Payment outcome is unknown; reconcile before any retry')
        if retry:
            if sub.status not in ['FAILED','CHECKOUT_FAILED']:raise HTTPException(409,'Only a definitively failed attempt can be retried')
            if len(prior)>=self.max_attempts:raise HTTPException(409,'Retry limit reached')
            if prior and prior[-1].retry_after and aware(prior[-1].retry_after)>utc():raise HTTPException(409,'Retry backoff has not elapsed')
        elif prior:return prior[-1]
        elif sub.status!='AUTHORIZED':raise HTTPException(409,'Merchant payment is not authorized')
        attempt=PaymentAttempt(intent_id=payment.id,idempotency_key=key,status='PROCESSING',simulation=simulation,attempt_number=len(prior)+1)
        expected=['FAILED','CHECKOUT_FAILED'] if retry else ['AUTHORIZED']
        changed=db.execute(update(MerchantSuborder).where(MerchantSuborder.id==sub.id,MerchantSuborder.status.in_(expected)).values(status='PROCESSING'))
        if changed.rowcount!=1:db.rollback();raise HTTPException(409,'Merchant authorization changed before execution')
        db.add(attempt);sub.status='PROCESSING';payment.status='PROCESSING'
        TraceRecorder(db,plan.id,plan.session_id).record('payment_attempt','PROCESSING',{'suborder_id':sub.id,'attempt':attempt.attempt_number})
        try:db.commit()
        except IntegrityError:
            db.rollback();raise HTTPException(409,'Another payment attempt is already in progress; reconcile its result')
        # The durable attempt is committed before contacting the provider. A crash leaves PROCESSING, never an assumed failure.
        if simulation=='checkout_failure':outcome='CHECKOUT_FAILED'
        else:
            provider=MockPaymentProvider(db.get_bind())
            try:outcome=provider.execute(amount=payment.amount,idempotency_key=key,simulation=simulation)
            except Exception:outcome='UNKNOWN'
        if lease and not self.owns(db,purchase,lease):
            db.expire_all()
            return attempt
        attempt.status=outcome;sub.status=outcome;payment.status=outcome
        if outcome in ['FAILED','CHECKOUT_FAILED']:attempt.retry_after=utc()+self.retry_delay
        TraceRecorder(db,plan.id,plan.session_id).record('payment_attempt',outcome,{'suborder_id':sub.id,'attempt':attempt.attempt_number})
        aggregate(db,purchase);db.commit()
        return attempt

    def execute(self,db,purchase_id,request,ai):
        if settings.payment_mode!='mock':raise HTTPException(503,'Only the mock payment adapter is configured')
        purchase,plan=purchase_for(db,purchase_id)
        PaymentAuthorizationService().verify(db,purchase)
        if purchase.status in ['APPROVAL_INVALIDATED','REJECTED','COMPENSATED','COMPENSATION_PENDING','PAYMENT_FAILED']:
            if purchase.execution_key==request.idempotency_key and purchase.execution_modes==request.simulations:return purchase
            raise HTTPException(409,'Purchase cannot execute in its current state')
        merchant_ids={s.merchant_id for s in suborders(db,purchase)}
        if set(request.simulations)-merchant_ids:raise HTTPException(422,'Unknown merchant simulation target')
        if purchase.execution_key:
            if purchase.execution_key!=request.idempotency_key or purchase.execution_modes!=request.simulations:raise HTTPException(409,'Execution idempotency key or inputs changed')
        else:
            purchase.execution_key=request.idempotency_key;purchase.execution_modes=request.simulations
            try:db.commit()
            except IntegrityError:db.rollback();raise HTTPException(409,'Execution idempotency key is already used')
        lease=self.acquire(db,purchase)
        for sub in suborders(db,purchase):
            if not self.owns(db,purchase,lease):break
            if sub.status in ['CAPTURED','FAILED','CHECKOUT_FAILED','REFUNDED','CANCELLED','REFUND_PENDING']:continue
            if sub.status in ['UNKNOWN','PROCESSING']:break
            try:sessions.ensure_current(db,plan,purchase.snapshot,ai)
            except HTTPException:
                for remaining in suborders(db,purchase):
                    if remaining.status=='AUTHORIZED':remaining.status='CANCELLED';intent_for(db,remaining).status='CANCELLED'
                purchase.status='APPROVAL_INVALIDATED' if not any(s.status=='CAPTURED' for s in suborders(db,purchase)) else 'PARTIAL_FAILURE'
                self.release(db,purchase,lease);db.commit();raise
            key=hashlib.sha256((purchase.id+':'+request.idempotency_key+':'+sub.id).encode()).hexdigest()
            self.execute_suborder(db,purchase,plan,sub,key,request.simulations.get(sub.merchant_id,'success'),lease=lease)
            if sub.status=='UNKNOWN':break
        self.release(db,purchase,lease)
        aggregate(db,purchase);db.commit();return purchase

    def retry(self,db,suborder_id,request,ai):
        sub=db.get(MerchantSuborder,suborder_id)
        if not sub:raise HTTPException(404,'Merchant suborder not found')
        purchase,plan=purchase_for(db,sub.purchase_id)
        if purchase.status in ['COMPENSATED','COMPENSATION_PENDING','APPROVAL_INVALIDATED','REJECTED']:raise HTTPException(409,'Purchase cannot be retried')
        PaymentAuthorizationService().verify(db,purchase)
        sessions.ensure_current(db,plan,purchase.snapshot,ai)
        key=hashlib.sha256((sub.id+':retry:'+request.idempotency_key).encode()).hexdigest()
        if any(s.status in ['UNKNOWN','PROCESSING'] for s in suborders(db,purchase)):raise HTTPException(409,'Reconcile unknown outcomes before retrying')
        lease=self.acquire(db,purchase)
        try:self.execute_suborder(db,purchase,plan,sub,key,request.simulation,retry=True,lease=lease)
        finally:
            self.release(db,purchase,lease)
            aggregate(db,purchase);db.commit()
        return purchase


class PaymentReconciliationService:
    def reconcile(self,db,purchase_id):
        purchase,plan=purchase_for(db,purchase_id)
        # Fence any previous worker before examining provider receipts. A late response cannot dispatch more charges.
        purchase.execution_token=None;db.commit()
        for sub in suborders(db,purchase):
            payment=intent_for(db,sub);attempts=attempts_for(db,payment)
            if not attempts:continue
            attempt=attempts[-1]
            if sub.status not in ['UNKNOWN','PROCESSING','REFUND_PENDING']:continue
            db.commit()
            outcome=MockPaymentProvider(db.get_bind()).lookup(attempt.idempotency_key,payment.amount)
            db.add(ReconciliationRecord(attempt_id=attempt.id,outcome=outcome))
            if outcome in ['CAPTURED','FAILED','REFUNDED','REFUND_PENDING']:
                sub.status=outcome;payment.status=outcome;attempt.status=outcome
                if outcome=='FAILED':attempt.retry_after=utc()+PaymentExecutionService.retry_delay
            else:sub.status='UNKNOWN';payment.status='UNKNOWN';attempt.status='UNKNOWN'
            TraceRecorder(db,plan.id,plan.session_id).record('reconciliation',outcome,{'suborder_id':sub.id})
            aggregate(db,purchase);db.commit()
        return purchase

    def compensate(self,db,purchase_id,pending=False):
        purchase,plan=purchase_for(db,purchase_id)
        if purchase.execution_token:raise HTTPException(409,'Execution is active; reconcile it before compensation')
        if any(s.status in ['UNKNOWN','PROCESSING'] for s in suborders(db,purchase)):raise HTTPException(409,'Reconcile unknown charges before compensation')
        if purchase.status not in ['PARTIAL_FAILURE','PAID','COMPENSATION_PENDING','COMPENSATED']:raise HTTPException(409,'No captured mock payment to compensate')
        worker=PaymentExecutionService();lease=worker.acquire(db,purchase)
        for sub in suborders(db,purchase):
            if sub.status in ['CAPTURED','REFUND_PENDING']:
                payment=intent_for(db,sub);attempt=attempts_for(db,payment)[-1]
                db.commit();outcome=MockPaymentProvider(db.get_bind()).compensate(attempt.idempotency_key,pending)
                sub.status=outcome;payment.status=outcome;attempt.status=outcome
                TraceRecorder(db,plan.id,plan.session_id).record('mock_compensation',outcome,{'suborder_id':sub.id})
            elif sub.status=='AUTHORIZED':sub.status='CANCELLED';intent_for(db,sub).status='CANCELLED'
        worker.release(db,purchase,lease)
        aggregate(db,purchase);db.commit();return purchase
