from decimal import Decimal
from collections import defaultdict
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.commerce import CommercePurchase,MerchantSuborder,CommercePlan,PaymentIntentRecord,PaymentAttempt,MockProviderReceipt,ReconciliationRecord
from app.commerce.payments import PaymentIntentService,suborders,intent_for,attempts_for,purchase_for
from app.commerce import sessions
from app.commerce.tracing import TraceRecorder


def create_purchase(db,request,ai):
    existing=db.scalar(select(CommercePurchase).where(CommercePurchase.idempotency_key==request.idempotency_key))
    if existing:
        if existing.plan_id!=request.plan_id or existing.alternative_index!=request.alternative_index:raise HTTPException(409,'Purchase key reused for different selection')
        return existing
    plan=sessions.plan_for(db,request.plan_id)
    context=sessions.session_for(db,plan.session_id)
    if context.latest_plan_id!=plan.id:raise HTTPException(409,{'message':'A newer plan exists','revised_plan_id':context.latest_plan_id})
    choices=plan.result.get('combinations',[])
    if request.alternative_index>=len(choices):raise HTTPException(422,'Unknown purchase alternative')
    snapshot=choices[request.alternative_index]
    sessions.ensure_current(db,plan,snapshot,ai)
    active=db.scalars(select(CommercePurchase).join(CommercePlan,CommercePurchase.plan_id==CommercePlan.id).where(CommercePlan.session_id==context.id,CommercePurchase.status.in_(['EXECUTING','PAYMENT_UNKNOWN','PARTIAL_FAILURE','COMPENSATION_PENDING'])))
    if list(active):raise HTTPException(409,'Reconcile or compensate the previous partial/unknown purchase before creating replacement orders')
    grouped=defaultdict(list)
    for line in snapshot['items']:grouped[line['offer']['merchant_id']].append(line)
    amount=sum((Decimal(i['line_total']) for i in snapshot['items']),Decimal('0.00'))
    if amount!=Decimal(snapshot['total']) or amount>Decimal(plan.intent['total_budget']):raise HTTPException(409,'Server-side total does not match plan budget')
    purchase=CommercePurchase(plan_id=plan.id,snapshot=snapshot,amount=amount,status='PENDING_APPROVAL',idempotency_key=request.idempotency_key,alternative_index=request.alternative_index)
    try:
        db.add(purchase);db.flush()
        for merchant_id,items in sorted(grouped.items()):db.add(MerchantSuborder(purchase_id=purchase.id,merchant_id=merchant_id,amount=sum((Decimal(i['line_total']) for i in items),Decimal('0.00')),items=items))
        db.flush();PaymentIntentService().create(db,purchase)
        TraceRecorder(db,plan.id,plan.session_id).record('prepare_checkout','PENDING_APPROVAL',{'purchase_id':purchase.id})
        db.commit();return purchase
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Purchase idempotency key is already used')


def present_purchase(db,purchase):
    rows=[]
    for sub in suborders(db,purchase):
        payment=intent_for(db,sub)
        attempts=[{'id':a.id,'status':a.status,'attempt_number':a.attempt_number,'retry_after':a.retry_after.isoformat() if a.retry_after else None} for a in attempts_for(db,payment)]
        rows.append({'id':sub.id,'merchant_id':sub.merchant_id,'merchant_name':sub.items[0]['offer']['merchant_name'],'amount':format(sub.amount,'.2f'),
            'status':sub.status,'items':sub.items,'payment_intent_id':payment.id,'attempts':attempts})
    return {'id':purchase.id,'plan_id':purchase.plan_id,'status':purchase.status,'amount':format(purchase.amount,'.2f'),'snapshot':purchase.snapshot,
        'approved':bool(purchase.approved_at),'suborders':rows,'execution_key':purchase.execution_key,'execution_modes':purchase.execution_modes,
        'captured_total':format(sum((s.amount for s in suborders(db,purchase) if s.status=='CAPTURED'),Decimal('0.00')),'.2f'),
        'refunded_total':format(sum((s.amount for s in suborders(db,purchase) if s.status=='REFUNDED'),Decimal('0.00')),'.2f'),
        'workflow':purchase.workflow,'mode':'mock','warning':'No real funds moved. Partial, unknown and compensation-pending outcomes are not completed purchases.'}


def reject(db,purchase_id):
    purchase,plan=purchase_for(db,purchase_id)
    if purchase.status not in ['PENDING_APPROVAL','APPROVED']:raise HTTPException(409,'Cannot reject a purchase after execution has started')
    purchase.status='REJECTED';purchase.approved_at=None
    for sub in suborders(db,purchase):sub.status='CANCELLED';intent_for(db,sub).status='CANCELLED'
    TraceRecorder(db,plan.id,plan.session_id).record('approval','REJECTED',{'purchase_id':purchase.id})
    db.commit();return purchase


def resolve_demo_outcome(db,attempt_id,outcome):
    attempt=db.get(PaymentAttempt,attempt_id)
    if not attempt:raise HTTPException(404,'Payment attempt not found')
    payment=db.get(PaymentIntentRecord,attempt.intent_id)
    if payment.provider!='mock':raise HTTPException(409,'Only demo provider outcomes can be simulated')
    if attempt.status not in ['UNKNOWN','PROCESSING']:raise HTTPException(409,'Only unknown mock outcomes may be resolved')
    receipt=db.get(MockProviderReceipt,attempt.idempotency_key)
    if receipt and receipt.outcome not in ['UNKNOWN',outcome]:raise HTTPException(409,'Provider ledger already has a definitive different outcome; reconcile it')
    if receipt:receipt.outcome=outcome
    else:db.add(MockProviderReceipt(idempotency_key=attempt.idempotency_key,amount=payment.amount,outcome=outcome))
    db.commit()
    return {'attempt_id':attempt.id,'provider_outcome':outcome,'message':'Mock ledger updated. Reconcile the purchase before attempting any further payment.'}
