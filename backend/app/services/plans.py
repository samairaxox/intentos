from collections import Counter
from copy import deepcopy
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session
from app.models.entities import PurchasePlan, PurchaseSession, Cart, Product, Order, AuditEvent
from app.models.multi_schemas import MultiIntent
from app.agents.multi_workflow import planning_graph, checkout_graph
from app.services.catalog import LocalCatalogProvider
from app.services.budget_optimizer import candidates_for, summarize


def get_plan(db: Session, plan_id: str) -> PurchasePlan:
    plan=db.scalar(select(PurchasePlan).where(PurchasePlan.id==plan_id).with_for_update().execution_options(populate_existing=True))
    if not plan: raise HTTPException(404,"Purchase plan not found")
    return plan


def present(plan: PurchasePlan) -> dict:
    db=object_session(plan)
    order_ids=list(db.scalars(select(Order.id).join(Cart,Order.cart_id==Cart.id).where(Cart.plan_id==plan.id).order_by(Order.created_at.desc(),Order.id))) if db else []
    return {"id":plan.id,"session_id":plan.session_id,"parent_id":plan.parent_id,"revision":plan.revision,
            "status":plan.status,"intent":plan.intent,"result":plan.result,"workflow":plan.workflow,"changes":plan.changes,"order_ids":order_ids}


def generate(db: Session, *, text: str = "Structured purchasing requirements", intent: MultiIntent | None = None, ai=None, parent: PurchasePlan | None = None) -> PurchasePlan:
    initial={"text":text}
    if intent is not None: initial["intent"]=intent.model_dump()
    session=PurchaseSession(request=text,result={'kind':'multi'})
    db.add(session);db.flush()
    plan=PurchasePlan(session_id=session.id,parent_id=parent.id if parent else None,revision=parent.revision+1 if parent else 1,
        status='PLANNING',intent=initial.get('intent',{}),result={},workflow={**initial,'steps':[],'completed':[]},changes=[])
    db.add(plan);db.commit()
    return run_planning(db,plan,ai)


def run_planning(db,plan,ai=None,resume=False):
    from app.agents.checkpoints import rediscover_after_interruption,PlanningInterrupted
    from app.services.gemini import AIUnavailable
    from sqlalchemy.exc import SQLAlchemyError
    state=plan.workflow
    if resume:
        if plan.status not in ['INTERRUPTED','PLANNING']:return plan
        state=rediscover_after_interruption(state,'parse','validate')
    def save(s):
        plan.workflow=s;plan.intent=s.get('intent',{});plan.result=s.get('result',{});plan.status=s.get('status','PLANNING')
        db.get(PurchaseSession,plan.session_id).result={'kind':'multi','status':plan.status}
        db.commit()
    try:planning_graph(ai,LocalCatalogProvider(db),checkpoint=save).invoke(state)
    except SQLAlchemyError:
        db.rollback();raise
    except Exception as exc:
        db.rollback();plan.status='INTERRUPTED';db.commit()
        if isinstance(exc,HTTPException):raise
        import logging
        logging.getLogger(__name__).error('multi_planning_interrupted: %s',type(exc).__name__)
        error=exc if isinstance(exc,AIUnavailable) else PlanningInterrupted('Purchase planning interrupted; resume the saved plan')
        setattr(error,'purchase_plan_id',plan.id);raise error from exc
    return plan


def differences(db: Session, snapshot: dict, intent: MultiIntent, lock: bool = True) -> list[str]:
    changes=[]
    requirements={r.category:r for r in intent.items}
    # Lock products in stable ID order to serialize checkout against catalog updates.
    for line in sorted(snapshot.get("items",[]),key=lambda i:i["product"]["id"]):
        previous=line["product"]
        query=select(Product).where(Product.id==previous["id"]).execution_options(populate_existing=True)
        if lock: query=query.with_for_update()
        row=db.scalar(query)
        if not row:
            changes.append(f"{previous['name']}: removed from catalog");continue
        current=row.data
        if not current.get("available") or not current.get("seller_available",True): changes.append(f"{previous['name']}: product or seller unavailable")
        if current.get("stock",1)<line["quantity"]: changes.append(f"{previous['name']}: insufficient stock")
        for key in ["price","seller","currency","category","specifications","brand","model","name","processor_brand","processor","ram_gb","storage_gb","weight_kg","battery_hours","gpu","os"]:
            if current.get(key)!=previous.get(key): changes.append(f"{previous['name']}: {key} changed from {previous.get(key)} to {current.get(key)}")
        req=requirements.get(current.get("category"))
        if req:
            from app.services.budget_optimizer import matches
            if not matches(current,req,intent): changes.append(f"{previous['name']}: no longer meets mandatory requirements")
    return list(dict.fromkeys(changes))


def invalidate(db: Session, plan: PurchasePlan, changes: list[str]) -> None:
    plan.status="INVALIDATED"
    plan.changes=changes
    carts=list(db.scalars(select(Cart).where(Cart.plan_id==plan.id).with_for_update()))
    for cart in carts:
        cart.status="STALE"
        for order in db.scalars(select(Order).where(Order.cart_id==cart.id).with_for_update()):
            if order.status in ["PENDING_APPROVAL","APPROVED"]:
                order.status="CANCELLED"
                db.add(AuditEvent(order_id=order.id,event="APPROVAL_INVALIDATED"))
                db.add(AuditEvent(order_id=order.id,event="CANCELLED"))


def replan(db: Session, plan: PurchasePlan, intent: MultiIntent | None = None, changes: list[str] | None = None) -> PurchasePlan:
    if intent is None and plan.result.get("revised_plan_id"):
        return get_plan(db,plan.result["revised_plan_id"])
    replacement_intent=intent or MultiIntent.model_validate(plan.intent)
    old=(plan.result.get("combinations") or [{}])[0]
    reasons=changes or differences(db,old,MultiIntent.model_validate(plan.intent))
    if replacement_intent.model_dump()!=plan.intent: reasons.append("Budget or user preferences changed")
    if not reasons: reasons=["User requested a fresh catalog discovery and optimization"]
    invalidate(db,plan,reasons)
    revised=generate(db,intent=replacement_intent,parent=plan)
    new=(revised.result.get("combinations") or [{}])[0]
    old_ids=Counter({i["product"]["id"]:i["quantity"] for i in old.get("items",[])})
    new_ids=Counter({i["product"]["id"]:i["quantity"] for i in new.get("items",[])})
    revised.changes=reasons+[f"Removed units: {dict(old_ids-new_ids)}",f"Added units: {dict(new_ids-old_ids)}",f"Total changed from INR {old.get('total_cost',0):,} to INR {new.get('total_cost',0):,}. Fresh approval is required."]
    plan.result={**plan.result,"revised_plan_id":revised.id}
    db.commit()
    return revised


def ensure_current(db: Session, plan: PurchasePlan, snapshot: dict) -> None:
    if plan.status!="READY":
        raise HTTPException(409,{"message":"Plan is not valid for checkout","revised_plan_id":plan.result.get("revised_plan_id")})
    changes=differences(db,snapshot,MultiIntent.model_validate(plan.intent))
    if changes:
        revised=replan(db,plan,changes=changes)
        raise HTTPException(409,{"message":"Catalog changed. Approval invalidated; a revised plan is ready for review.","revised_plan_id":revised.id,"changes":revised.changes})


def validate_plan(db: Session, plan_id: str) -> dict:
    plan=get_plan(db,plan_id)
    if plan.status!="READY": return {"valid":False,"plan":present(plan),"revised_plan_id":plan.result.get("revised_plan_id")}
    snapshot=plan.result["combinations"][0]
    changes=differences(db,snapshot,MultiIntent.model_validate(plan.intent))
    if changes:
        revised=replan(db,plan,changes=changes)
        return {"valid":False,"plan":present(plan),"revised_plan_id":revised.id,"revised_plan":present(revised)}
    return {"valid":True,"plan":present(plan)}


def get_cart(db: Session, cart_id: str) -> Cart:
    cart=db.scalar(select(Cart).where(Cart.id==cart_id).with_for_update().execution_options(populate_existing=True))
    if not cart: raise HTTPException(404,"Cart not found")
    return cart


def present_cart(cart: Cart) -> dict:
    return {"id":cart.id,"plan_id":cart.plan_id,"alternative_index":cart.alternative_index,"version":cart.version,"status":cart.status,"snapshot":cart.snapshot}


def create_cart(db: Session, request) -> Cart:
    plan=get_plan(db,request.plan_id)
    combinations=plan.result.get("combinations",[])
    if request.alternative_index>=len(combinations): raise HTTPException(422,"Unknown alternative plan")
    snapshot=combinations[request.alternative_index]
    ensure_current(db,plan,snapshot)
    state=checkout_graph().invoke({**plan.workflow,"selected_index":request.alternative_index})
    plan.workflow=state
    cart=Cart(plan_id=plan.id,alternative_index=request.alternative_index,snapshot=deepcopy(state["selection"]))
    db.add(cart);db.commit()
    return cart


def update_cart(db: Session, cart_id: str, request) -> Cart:
    initial=db.get(Cart,cart_id)
    if not initial: raise HTTPException(404,"Cart not found")
    plan=get_plan(db,initial.plan_id)
    cart=get_cart(db,cart_id)
    if cart.status!="ACTIVE" or cart.version!=request.expected_version:
        raise HTTPException(409,"Cart is stale, ordered or was changed in another request")
    ensure_current(db,plan,cart.snapshot)
    intent=MultiIntent.model_validate(plan.intent)
    products=LocalCatalogProvider(db).discover([r.category for r in intent.items])
    candidates=candidates_for(intent,products)
    by_id={p["id"]:p for values in candidates.values() for p in values}
    if any(pid not in by_id for pid in request.product_ids): raise HTTPException(422,"Cart contains ineligible products")
    selected=[by_id[pid] for pid in request.product_ids]
    counts=Counter(p["category"] for p in selected)
    for req in intent.items:
        if counts[req.category] not in ([req.quantity] if req.required else [0,req.quantity]):
            raise HTTPException(422,"Cart must preserve required quantities; optional quantities are all-or-none")
    stock=Counter(request.product_ids)
    if any(qty>by_id[pid].get("stock",1) for pid,qty in stock.items()): raise HTTPException(409,"Insufficient stock")
    snapshot=summarize(intent,selected,candidates)
    if snapshot["total_cost"]>intent.total_budget: raise HTTPException(422,"Cart exceeds total budget")
    # Lock/recheck newly selected catalog records before accepting their snapshots.
    ensure_current(db,plan,snapshot)
    cart.snapshot=snapshot;cart.version+=1
    db.commit()
    return cart
