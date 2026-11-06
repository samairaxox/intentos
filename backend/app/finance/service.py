from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.entities import PurchaseSession
from app.models.commerce import CommerceSession, CommercePlan, CommercePurchase, MerchantSuborder
from app.models.finance import FinancialDecision, FinancialPlanLink, ScenarioSimulation
from app.commerce import sessions, checkout
from app.commerce.schemas import PurchaseCreate, CanonicalProduct, MerchantOffer
from app.finance.schemas import FinancialGoal
from app.finance.workflow import run
from app.finance.engine import simulate
from app.finance.history import history


def decision_for(db,decision_id):
    row=db.get(FinancialDecision,decision_id)
    if not row: raise HTTPException(404,'Financial decision not found')
    sessions.session_for(db,row.session_id)
    db.refresh(row)
    return row


def is_financial(db,session_id):
    root=db.get(PurchaseSession,session_id)
    return bool(root and root.result.get('kind')=='financial')


def assert_latest(db,decision):
    root=db.get(PurchaseSession,decision.session_id)
    db.refresh(root)
    if root.result.get('latest_decision_id')!=decision.id:
        raise HTTPException(409,{'message':'Financial decision superseded','revised_decision_id':root.result.get('latest_decision_id')})


def present(db,row):
    root=db.get(PurchaseSession,row.session_id)
    return {'id':row.id,'session_id':row.session_id,'parent_id':row.parent_id,'status':row.status,'goal':row.goal or None,
        'result':{'status':row.status,'hypothetical':False,'recommended':None,'strategies':[],
            'explanation':'Decision is incomplete. Resume the workflow or submit an explicit revised goal.',
            'assumptions':[],'change_triggers':[],**row.result},'workflow':{'completed':row.workflow.get('completed',[])},
        'histories':row.workflow.get('histories',{}),'latest_decision_id':root.result.get('latest_decision_id'),
        'purchase_ids':list(db.scalars(select(CommercePurchase.id).join(CommercePlan).where(CommercePlan.session_id==row.session_id).order_by(CommercePurchase.created_at.desc()))),
        'scenarios':[{'id':s.id,'parameters':s.parameters,'result':s.result} for s in db.scalars(select(ScenarioSimulation).where(ScenarioSimulation.decision_id==row.id))]}


def create(db,request,ai):
    root=PurchaseSession(request=(request.text or 'Structured financial goal')[:4000],result={'kind':'financial'})
    db.add(root);db.flush()
    session=CommerceSession(id=root.id,intent={},conversation=[],version=0)
    db.add(session);db.flush()
    decision=FinancialDecision(session_id=session.id,goal=request.goal.model_dump(mode='json') if request.goal else {},
        workflow={'text':request.text or '', 'goal':request.goal.model_dump(mode='json') if request.goal else {},'ai_used':bool(request.text),'completed':[]})
    db.add(decision);db.flush();root.result={**root.result,'latest_decision_id':decision.id};db.commit()
    return run(db,decision,ai)


def revise(db,old,goal,ai):
    assert_latest(db,old)
    for plan in db.scalars(select(CommercePlan).where(CommercePlan.session_id==old.session_id)):
        sessions.invalidate(db,plan,['Financial goal changed; fresh financial decision and approval required'])
    old.status='SUPERSEDED'
    decision=FinancialDecision(session_id=old.session_id,parent_id=old.id,goal=goal.model_dump(mode='json'),
        workflow={'goal':goal.model_dump(mode='json'),'ai_used':False,'completed':[]})
    db.add(decision);db.flush()
    root=db.get(PurchaseSession,old.session_id);root.result={**root.result,'latest_decision_id':decision.id}
    db.commit()
    return run(db,decision,ai)


def policy_check(db,plan,snapshot,*,purchase_id=None,exposure=False):
    link=db.get(FinancialPlanLink,plan.id)
    if not link:
        if is_financial(db,plan.session_id): raise HTTPException(409,'Financial session requires a linked strategy')
        return
    decision=decision_for(db,link.decision_id);assert_latest(db,decision)
    goal=FinancialGoal.model_validate(decision.goal)
    total=sum((Decimal(line['line_total']) for line in snapshot['items']),Decimal(0))
    if total!=Decimal(snapshot['total']) or total>goal.spendable: raise HTTPException(409,'Financial reserve would be violated')
    for category,cap in goal.category_limits.items():
        if sum(Decimal(l['line_total']) for l in snapshot['items'] if l['product']['category']==category)>cap:
            raise HTTPException(409,'Category spending limit exceeded')
    if exposure:
        committed,categories=commitments(db,plan.session_id,exclude_purchase_id=purchase_id)
        if total+committed>goal.spendable: raise HTTPException(409,'Existing financial commitments leave insufficient spendable budget')
        for category,cap in goal.category_limits.items():
            allocated=sum(Decimal(l['line_total']) for l in snapshot['items'] if l['product']['category']==category)
            if allocated+categories.get(category,Decimal(0))>cap: raise HTTPException(409,'Existing commitments exceed category spending capacity')


def commitments(db,session_id,exclude_purchase_id=None):
    # Captures, unknown outcomes and refund-pending money remain encumbered.
    purchases=list(db.scalars(select(CommercePurchase).join(CommercePlan).where(CommercePlan.session_id==session_id)))
    total=Decimal(0);categories={}
    for purchase in purchases:
        if purchase.id==exclude_purchase_id: continue
        for sub in db.scalars(select(MerchantSuborder).where(MerchantSuborder.purchase_id==purchase.id)):
            if sub.status in ['CAPTURED','REFUND_PENDING','UNKNOWN','PROCESSING','AUTHORIZED','PENDING_APPROVAL']:
                total+=sub.amount
                for line in sub.items:
                    category=line['product']['category']
                    categories[category]=categories.get(category,Decimal(0))+Decimal(line['line_total'])
    return total,categories



def select_strategy(db,decision,request,ai):
    assert_latest(db,decision)
    existing=db.scalar(select(CommercePurchase).where(CommercePurchase.idempotency_key==request.idempotency_key))
    if existing:
        link=db.get(FinancialPlanLink,existing.plan_id)
        if not link or link.decision_id!=decision.id or link.strategy!=request.strategy: raise HTTPException(409,'Selection key already used')
        return existing
    if decision.status!='AWAITING_DECISION': raise HTTPException(409,'Decision is not ready for selection')
    strategy=next((s for s in decision.result.get('strategies',[]) if s['code']==request.strategy),None)
    if not strategy or not strategy['executable']: raise HTTPException(422,'Only a feasible current purchase strategy can enter checkout')
    session=sessions.session_for(db,decision.session_id)
    if session.latest_plan_id:
        sessions.invalidate(db,db.get(CommercePlan,session.latest_plan_id),['Different financial strategy selected; approval required'])
    goal=FinancialGoal.model_validate(decision.goal)
    intent=goal.commerce_intent()
    if request.strategy=='essentials_now': intent=intent.model_copy(update={'items':[r for r in intent.items if r.required]})
    session.version+=1;session.intent=intent.model_dump(mode='json')
    plan=CommercePlan(session_id=session.id,version=session.version,status='AWAITING_SELECTION',intent=session.intent,
        result={'status':'READY','combinations':[strategy['plan']]},workflow={'completed':['financial_strategy_selected']},changes=[])
    db.add(plan);db.flush();session.latest_plan_id=plan.id
    db.add(FinancialPlanLink(plan_id=plan.id,decision_id=decision.id,strategy=request.strategy));db.flush()
    sessions.save_snapshots(db,plan)
    db.commit()
    return checkout.create_purchase(db,PurchaseCreate(plan_id=plan.id,alternative_index=0,idempotency_key=request.idempotency_key),ai)


def scenario(db,decision,spec):
    goal=FinancialGoal.model_validate(decision.goal)
    # Replay the decision's persisted market snapshot, explicitly hypothetical.
    result=simulate(goal,[CanonicalProduct.model_validate(p) for p in decision.workflow.get('products',[])],
        [MerchantOffer.model_validate(o) for o in decision.workflow.get('offers',[])],decision.workflow.get('histories',{}),spec,datetime.fromisoformat(decision.workflow['at']) if decision.workflow.get('at') else None)
    row=ScenarioSimulation(decision_id=decision.id,parameters=spec.model_dump(mode='json'),result=result)
    db.add(row);db.commit()
    return {'id':row.id,'parameters':row.parameters,'result':row.result}
