from time import perf_counter
from typing import TypedDict
from langgraph.graph import StateGraph,START,END
from app.commerce.schemas import CommerceIntent,CanonicalProduct,MerchantOffer
from app.commerce.store import discover_and_persist,current_offer
from app.commerce.pricing import TotalCostService
from app.services.optimization import satisfies
from app.commerce.freshness import OfferFreshnessService
from app.commerce.optimizer import optimize_offers
from app.commerce.tracing import TraceRecorder

class CommerceState(TypedDict,total=False):
    text:str
    intent:dict
    ai_used:bool
    completed:list[str]
    products:list[dict]
    offers:list[dict]
    offer_ids:list[str]
    eligible_offers:list[dict]
    warnings:list[str]
    result:dict
    status:str


def commerce_graph(db,plan,ai):
    trace=TraceRecorder(db,plan.id,plan.session_id)
    def parse(s):
        intent=CommerceIntent.model_validate(s['intent']) if s.get('intent') else ai.parse(s['text'])
        return {'intent':intent.model_dump(mode='json')}
    def validate(s):
        missing=CommerceIntent.model_validate(s['intent']).missing()
        return {'status':'NEEDS_DETAILS' if missing else 'DISCOVERING','result':{'missing_information':missing,'combinations':[]}}
    def discover(s):
        found=discover_and_persist(db,[r['category'] for r in s['intent']['items']])
        trace.record('provider_request','COMPLETED',{'provider_id':'demo-catalog','product_count':len(found.products),'offer_count':len(found.offers)})
        return {'products':[p.model_dump(mode='json') for p in found.products],'offer_ids':[o.id for o in found.offers],'warnings':found.warnings}
    def retrieve(s):
        offers=[current_offer(db,oid) for oid in s['offer_ids']]
        return {'offers':[o.model_dump(mode='json') for o in offers if o]}
    def normalize(s):
        products=[CanonicalProduct.model_validate(p).model_dump(mode='json') for p in s['products']]
        offers=[MerchantOffer.model_validate(o).model_dump(mode='json') for o in s['offers']]
        return {'products':products,'offers':offers}
    def freshness(s):
        eligible=[o for o in s['offers'] if OfferFreshnessService().inspect(MerchantOffer.model_validate(o))['checkout_eligible']]
        by_id={p['id']:p for p in s['products']}
        views=[{'offer':o,'product':by_id[o['product_id']],'pricing':TotalCostService().calculate(MerchantOffer.model_validate(o)),'freshness':OfferFreshnessService().inspect(MerchantOffer.model_validate(o))} for o in s['offers'] if o['product_id'] in by_id]
        return {'status':'ELIGIBLE' if eligible else 'STALE_OFFERS' if s['offers'] else 'NO_PRODUCTS','result':{**s['result'],'offers':views}}
    def eligibility(s):
        intent=CommerceIntent.model_validate(s['intent']);reqs={r.category:r for r in intent.items};by_id={p['id']:p for p in s['products']}
        accepted=[]
        for raw in s['offers']:
            offer=MerchantOffer.model_validate(raw);product=by_id.get(offer.product_id)
            if not product or not OfferFreshnessService().inspect(offer)['checkout_eligible']:continue
            if intent.allowed_merchants and offer.merchant_id not in intent.allowed_merchants:continue
            if offer.merchant_id in intent.blocked_merchants:continue
            if all(satisfies({**product['specifications'],'brand':product['brand']},r) for r in reqs[product['category']].hard_constraints):accepted.append(raw)
        return {'eligible_offers':accepted}
    def optimize(s):
        result=optimize_offers(CommerceIntent.model_validate(s['intent']),[CanonicalProduct.model_validate(p) for p in s['products']],[MerchantOffer.model_validate(o) for o in s['offers']])
        return {'result':result,'status':result['status']}
    def explain(s):
        result=dict(s['result'])
        if s.get('ai_used') and result.get('combinations'):result['combinations']=ai.explain(result['combinations'])
        return {'result':result}
    def await_approval(s):return {'status':'AWAITING_SELECTION' if s['status']=='READY' else s['status']}
    graph=StateGraph(CommerceState)
    for name,fn in {'understand_intent':parse,'validate_constraints':validate,'discover_products':discover,'retrieve_offers':retrieve,'normalize_offers':normalize,'check_freshness':freshness,'evaluate_eligibility':eligibility,'optimize_plan':optimize,'generate_explanation':explain,'await_user_approval':await_approval}.items():
        def wrapped(state, name=name,fn=fn):
            if name in state.get('completed',[]):return {}
            started=perf_counter()
            try:
                changes=fn(state)
                changes['completed']=state.get('completed',[])+[name]
                checkpoint={**state,**changes}
                plan.workflow=checkpoint;plan.intent=checkpoint.get('intent',{})
                plan.result=checkpoint.get('result',{});plan.status=checkpoint.get('status','PLANNING')
                details={'duration_ms':round((perf_counter()-started)*1000,3)}
                if name in ['understand_intent','generate_explanation']:details.update(getattr(getattr(ai,'service',None),'last_usage',{}))
                trace.record(name,'COMPLETED',details)
                db.commit()
                return changes
            except Exception as exc:
                db.rollback();plan.status='INTERRUPTED'
                trace.record(name,'ERROR',{'duration_ms':round((perf_counter()-started)*1000,3),'error_type':type(exc).__name__})
                db.commit();raise
        graph.add_node(name,wrapped)
    graph.add_edge(START,'understand_intent');graph.add_edge('understand_intent','validate_constraints')
    graph.add_conditional_edges('validate_constraints',lambda s:'stop' if s['status']=='NEEDS_DETAILS' else 'continue',{'stop':END,'continue':'discover_products'})
    order=['discover_products','retrieve_offers','normalize_offers','check_freshness','evaluate_eligibility','optimize_plan','generate_explanation','await_user_approval']
    for left,right in zip(order,order[1:]):
        if left=='check_freshness':graph.add_conditional_edges(left,lambda s:'stop' if s['status'] in ['STALE_OFFERS','NO_PRODUCTS'] else 'continue',{'stop':'await_user_approval','continue':right})
        else:graph.add_edge(left,right)
    graph.add_edge(order[-1],END)
    return graph.compile()


def run_planning(db,plan,ai):
    initial=plan.workflow or {'intent':plan.intent,'completed':[],'ai_used':False}
    return commerce_graph(db,plan,ai).invoke(initial)
