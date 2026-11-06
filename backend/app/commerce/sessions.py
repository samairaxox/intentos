from copy import deepcopy
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.entities import PurchaseSession,Product
from app.models.commerce import CommerceSession,CommercePlan,OfferSnapshot,CommercePurchase,MerchantSuborder,PaymentIntentRecord
from app.commerce.schemas import CommerceIntent,PreferencePatch,CanonicalProduct,utc
from app.commerce.workflow import run_planning
from app.commerce.store import current_offer
from app.commerce.freshness import OfferFreshnessService
from app.commerce.pricing import TotalCostService
from app.commerce.tracing import TraceRecorder


def session_for(db,session_id):
    row=db.scalar(select(CommerceSession).where(CommerceSession.id==session_id).with_for_update().execution_options(populate_existing=True))
    if not row:raise HTTPException(404,'Commerce session not found')
    return row


def plan_for(db,plan_id):
    row=db.get(CommercePlan,plan_id)
    if not row:raise HTTPException(404,'Commerce plan not found')
    session_for(db,row.session_id)
    db.refresh(row)
    return row


def merge_preferences(intent:CommerceIntent,patch:PreferencePatch) -> CommerceIntent:
    data=deepcopy(intent.model_dump(mode='json'))
    for key in ['total_budget','spending_preference','allowed_merchants','blocked_merchants']:
        value=getattr(patch,key)
        if value is not None:data[key]=value
    if patch.weights:
        data['weights']={**data['weights'],**patch.weights.model_dump(exclude_none=True)}
    items={item['category']:item for item in data['items']}
    for change in patch.items:
        if change.remove:
            items.pop(change.category,None);continue
        item=items.setdefault(change.category,{'category':change.category,'quantity':1,'required':True,'priority':3,'hard_constraints':[],'soft_preferences':[]})
        for key in ['quantity','required','priority']:
            value=getattr(change,key)
            if value is not None:item[key]=value
        for key,remove in [('hard_constraints',change.remove_hard_fields),('soft_preferences',change.remove_soft_fields)]:
            rules={(rule['field'],rule['operator']):rule for rule in item[key] if rule['field'] not in remove}
            for rule in getattr(change,key) or []:rules[(rule.field,rule.operator)]=rule.model_dump(mode='json')
            item[key]=list(rules.values())
    data['items']=list(items.values())
    return CommerceIntent.model_validate(data)


def present_plan(db,plan):
    purchases=list(db.scalars(select(CommercePurchase.id).where(CommercePurchase.plan_id==plan.id).order_by(CommercePurchase.created_at.desc())))
    return {'id':plan.id,'session_id':plan.session_id,'parent_id':plan.parent_id,'version':plan.version,'status':plan.status,
        'intent':plan.intent,'result':plan.result,'workflow':plan.workflow,'changes':plan.changes,'purchase_ids':purchases}


def present_session(db,row):
    plans=list(db.scalars(select(CommercePlan).where(CommercePlan.session_id==row.id).order_by(CommercePlan.version)))
    return {'id':row.id,'version':row.version,'intent':row.intent,'conversation':row.conversation,'latest_plan_id':row.latest_plan_id,
        'plans':[{'id':p.id,'version':p.version,'status':p.status} for p in plans]}


def save_snapshots(db,plan):
    existing=set(db.scalars(select(OfferSnapshot.offer_id).where(OfferSnapshot.plan_id==plan.id)))
    for combo in plan.result.get('combinations',[]):
        for line in combo['items']:
            if line['offer']['id'] not in existing:
                db.add(OfferSnapshot(plan_id=plan.id,offer_id=line['offer']['id'],data=line));existing.add(line['offer']['id'])


def create_session(db,request,ai):
    root=PurchaseSession(request=request.text or 'Explicit structured commerce requirements',result={'kind':'commerce'})
    db.add(root);db.flush()
    session=CommerceSession(id=root.id,intent=request.intent.model_dump(mode='json') if request.intent else {},conversation=[{'role':'user','text':request.text or 'Structured requirements supplied'}],version=1)
    db.add(session);db.flush()
    plan=CommercePlan(session_id=session.id,version=1,status='PLANNING',intent=session.intent,result={},workflow={'text':request.text or '', 'intent':session.intent,'ai_used':bool(request.text),'completed':[]})
    db.add(plan);db.flush();session.latest_plan_id=plan.id;db.commit()
    run_planning(db,plan,ai)
    session.intent=plan.intent;save_snapshots(db,plan);db.commit()
    return session,plan


def invalidate(db,plan,reasons):
    plan.status='INVALIDATED';plan.changes=reasons
    for purchase in db.scalars(select(CommercePurchase).where(CommercePurchase.plan_id==plan.id).with_for_update()):
        if purchase.status in ['PENDING_APPROVAL','APPROVED']:
            purchase.status='APPROVAL_INVALIDATED';purchase.approved_at=None
            for sub in db.scalars(select(MerchantSuborder).where(MerchantSuborder.purchase_id==purchase.id)):
                sub.status='CANCELLED'
                payment=db.scalar(select(PaymentIntentRecord).where(PaymentIntentRecord.suborder_id==sub.id))
                if payment:payment.status='CANCELLED'
            TraceRecorder(db,plan.id,plan.session_id).record('approval','INVALIDATED',{'purchase_id':purchase.id})


def new_version(db,session,intent,ai,reasons,ai_used=False):
    old=plan_for(db,session.latest_plan_id)
    invalidate(db,old,reasons)
    session.version+=1;session.intent=intent.model_dump(mode='json')
    plan=CommercePlan(session_id=session.id,parent_id=old.id,version=session.version,status='PLANNING',intent=session.intent,result={},
        workflow={'intent':session.intent,'ai_used':ai_used,'completed':[]},changes=reasons+['Fresh approval is required for all changed purchase terms.'])
    db.add(plan);db.flush();session.latest_plan_id=plan.id;db.commit()
    run_planning(db,plan,ai);save_snapshots(db,plan);db.commit()
    return plan


def update_session(db,session_id,request,ai):
    session=session_for(db,session_id)
    if session.version!=request.expected_version:raise HTTPException(409,'Session version changed; reload before applying preferences')
    intent=CommerceIntent.model_validate(session.intent)
    patch=request.patch or ai.patch(request.text,session.intent)
    updated=merge_preferences(intent,patch)
    if updated==intent:raise HTTPException(422,'No explicit preference change was supplied')
    session.conversation=session.conversation+[{'role':'user','text':request.text or 'Explicit preference patch','patch':patch.model_dump(mode='json',exclude_none=True)}]
    return new_version(db,session,updated,ai,['Session preferences changed; unrelated constraints were retained'],ai_used=bool(request.text))


def material_changes(db,snapshot):
    changes=[]
    for line in snapshot.get('items',[]):
        old=line['offer'];current=current_offer(db,old['id'])
        if not current:changes.append(f"Offer {old['id']} was removed");continue
        if not OfferFreshnessService().inspect(current)['checkout_eligible']:changes.append(f"Offer {old['id']} is expired, unverified or unavailable")
        from app.commerce.schemas import MerchantOffer
        if not OfferFreshnessService().inspect(MerchantOffer.model_validate(old))['fresh']:changes.append(f"Approved quote {old['id']} expired")
        if current.stock<line['quantity']:changes.append(f"Offer {old['id']} has insufficient stock")
        pricing=TotalCostService().calculate(current)
        for key in ['base_price','shipping','fees','estimated_taxes','confirmed_discount','final_price']:
            if pricing[key]!=line['pricing'][key]:changes.append(f"{old['id']}: {key} changed from {line['pricing'][key]} to {pricing[key]}")
        if current.product_id!=old['product_id'] or current.merchant_id!=old['merchant_id'] or current.currency!=old['currency']:changes.append(f"Material identity/currency changed for {old['id']}")
        product=db.get(Product,old['product_id'])
        if not product or any(product.data.get(key)!=line['product'].get(key) for key in ['brand','model','name','category']):changes.append(f"Product identity changed for {old['product_id']}")
        if product:
            actual={**product.data.get('specifications',{})}
            for key in ['processor_brand','ram_gb','storage_gb','weight_kg','battery_hours','gpu','os']:
                if key in product.data:actual[key]=product.data[key]
            if actual!=line['product']['specifications']:changes.append(f"Specifications changed for {old['product_id']}")
    return list(dict.fromkeys(changes))


def replan(db,plan,ai,reasons=None):
    session=session_for(db,plan.session_id)
    if session.latest_plan_id!=plan.id:return plan_for(db,session.latest_plan_id)
    return new_version(db,session,CommerceIntent.model_validate(session.intent),ai,reasons or ['Explicit discovery refresh requested'])


def ensure_current(db,plan,snapshot,ai):
    if plan.status!='AWAITING_SELECTION':
        session=session_for(db,plan.session_id)
        raise HTTPException(409,{'message':'Plan is not valid for checkout','revised_plan_id':session.latest_plan_id if session.latest_plan_id!=plan.id else None})
    reasons=material_changes(db,snapshot)
    if reasons:
        revised=replan(db,plan,ai,reasons)
        raise HTTPException(409,{'message':'Approved offers changed. Review revised terms and approve again.','revised_plan_id':revised.id,'changes':reasons})
