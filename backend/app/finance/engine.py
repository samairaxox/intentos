"""Evidence-grounded planning. Risk indices are policy penalties, never probabilities."""
from copy import deepcopy
from decimal import Decimal
from time import perf_counter
from app.commerce.schemas import aware, utc, MerchantOffer
from app.commerce.pricing import TotalCostService
from app.commerce.optimizer import optimize_offers
from app.finance.schemas import FinancialGoal


def cash(value): return format(Decimal(value).quantize(Decimal('.01')),'.2f')


def offer_risk(offer, observations, at):
    age=max(Decimal(0),Decimal(str((aware(at)-aware(offer.retrieved_at)).total_seconds())))
    freshness=min(Decimal(100),age/9)  # 15-minute quote lifetime maps to 100.
    provenance=Decimal(0 if offer.source_type=='live_verified' and offer.verification_status=='verified' else 35)
    stock=Decimal(70 if offer.stock<=2 else 25 if offer.stock<10 else 0)
    volatility=min(Decimal(100),Decimal(observations['volatility_percent'])*5) if observations.get('evidence')=='HISTORICAL_ONLY' else Decimal(30)
    score=volatility*Decimal('.3')+provenance*Decimal('.3')+freshness*Decimal('.2')+stock*Decimal('.2')
    return {'index':cash(score),'volatility':cash(volatility),'volatility_unknown':observations.get('evidence')!='HISTORICAL_ONLY',
        'freshness':cash(freshness),'stock_scarcity':cash(stock),'provenance':cash(provenance),
        'delivery':None,'delivery_status':'NOT_SUPPORTED','method':'offer-risk-v1: 30% volatility + 30% provenance + 20% quote age + 20% scarcity; unknown volatility penalty 30; not a probability or seller reputation'}


def basket_risk(combo, scores, spendable):
    total=Decimal(combo['total'])
    weighted=sum(Decimal(line['line_total'])*Decimal(scores[line['offer']['id']]['index']) for line in combo['items'])/max(Decimal('.01'),total)
    utilization=total/max(Decimal('.01'),spendable)*100
    concentration=max((Decimal(v) for v in combo['merchant_totals'].values()),default=Decimal(0))/max(Decimal('.01'),total)*100
    return {'index':cash(weighted*Decimal('.7')+utilization*Decimal('.15')+concentration*Decimal('.15')),
        'offer_weighted_index':cash(weighted),'budget_utilization_percent':cash(utilization),'largest_seller_percent':cash(concentration),
        'method':'70% cost-weighted offer risk + 15% budget utilization + 15% largest seller share; policy index, not confidence',
        'offers':{line['offer']['id']:scores[line['offer']['id']] for line in combo['items']},'delivery':'No verified delivery observations available'}


def waiting(goal, combo, histories, at, days=None):
    days=goal.patience_days if days is None else days
    result={'code':'wait','executable':False,'days':days,'status':'INSUFFICIENT_EVIDENCE',
        'forecast':None,'explanation':'No future discount is assumed. At least 8 observations across 7 distinct days spanning 7 days are required for historical comparison.'}
    if not combo: return result
    result['stock_at_risk']=any(line['offer']['stock']<=2 for line in combo['items'])
    if days<=0 or days>goal.patience_days or (goal.deadline and (goal.deadline-aware(at).date()).days<days):
        return {**result,'status':'WAIT_NOT_PERMITTED','explanation':'Waiting exceeds explicit patience or deadline.'}
    if not all(histories.get(line['offer']['id'],{}).get('evidence')=='HISTORICAL_ONLY' for line in combo['items']): return result
    observed_target=sum(Decimal(histories[line['offer']['id']]['minimum'])*line['quantity'] for line in combo['items'])
    target=goal.target_total if goal.target_total is not None else observed_target
    cost=goal.opportunity_cost_per_day*days
    return {**result,'status':'CONDITIONAL_HISTORICAL_COMPARISON','target_total':cash(target),
        'opportunity_cost':cash(cost),'conditional_net_difference':cash(Decimal(combo['total'])-target-cost),
        'history_mode':goal.history_mode,'explanation':'Conditional only: assumes the user target, or each selected offer historical minimum, becomes simultaneously available. This may never occur. Recheck stock, quotes and approval before purchase. Synthetic history is illustrative.'}


def evaluate(goal, products, offers, histories, at=None, hypothetical=False):
    at=at or utc()
    start=perf_counter()
    reserve={'available':cash(goal.total_budget or 0),'mandatory_reserve':cash(goal.mandatory_reserve),'spendable':cash(goal.spendable),
        'category_limits':{k:cash(v) for k,v in goal.category_limits.items()}}
    result={'reserve':reserve,'hypothetical':hypothetical,'strategies':[],'recommended':None,'history_mode':goal.history_mode,
        'assumptions':['Only current eligible landed unit prices are executable.','Reserve and category limits are hard constraints.',
        'Risk indices are documented policy penalties, not probabilities.','No verified delivery data or seller reputation is available.',
        'Past prices do not establish future prices. Separate purchases require new quotes and approval.'],
        'change_triggers':['Budget, reserve, constraints or risk preference changes','Quote expiry, price, stock or product changes','New price observations'],
        'missing_information':goal.missing()}
    if goal.missing(): return {**result,'status':'NEEDS_DETAILS'}
    scores={o.id:offer_risk(o,histories.get(o.id,{}),at) for o in offers}
    common={'limit':1,'budget_minor':int(goal.spendable*100),'category_limits_minor':{k:int(v*100) for k,v in goal.category_limits.items()},
        'risk_scores':{k:v['index'] for k,v in scores.items()},'as_of':at}
    intent=goal.commerce_intent()
    for code,profile in [('immediate','utility'),('lowest_price','cost_focused'),('optimized',goal.risk_strategy)]:
        solved=optimize_offers(intent,products,offers,objective_profile=profile,**common)
        combo=next(iter(solved['combinations']),None)
        strategy={'code':code,'profile':profile,'status':solved['status'],'executable':bool(combo) and not hypothetical,'plan':combo}
        if combo: strategy['risk']=basket_risk(combo,scores,goal.spendable)
        result['strategies'].append(strategy)
    optimized=result['strategies'][2]['plan']
    if any(not req.required for req in goal.items) and any(req.required for req in goal.items):
        essentials=intent.model_copy(update={'items':[r for r in intent.items if r.required]})
        solved=optimize_offers(essentials,products,offers,objective_profile=goal.risk_strategy,**common)
        combo=next(iter(solved['combinations']),None)
        result['strategies'].append({'code':'essentials_now','status':solved['status'],'executable':bool(combo) and not hypothetical,'plan':combo,
            'deferred_categories':[r.category for r in goal.items if not r.required],
            'explanation':'Buy only explicitly required items now. Optional items remain unpurchased and need a later decision and approval.',
            'risk':basket_risk(combo,scores,goal.spendable) if combo else None})
    result['wait']=waiting(goal,optimized,histories,at)
    result['recommended']='optimized' if optimized else None
    result['status']='AWAITING_DECISION' if optimized else 'NO_MATCH'
    result['explanation']=f"{goal.risk_strategy} optimization uses spendable INR {cash(goal.spendable)} and preserves INR {cash(goal.mandatory_reserve)}. "+(
        f"Current optimized total INR {optimized['total']}. Waiting status: {result['wait']['status']}. Review alternatives and explicitly approve before mock payment." if optimized else 'No feasible basket satisfies all hard constraints; reduce requirements or revise the spendable budget.')
    result['runtime_ms']=round((perf_counter()-start)*1000,3)
    return result


def simulate(goal, products, offers, histories, spec, at=None):
    data=goal.model_dump(mode='json')
    budget=(goal.total_budget or Decimal(0))-spec.budget_reduction
    if budget<goal.mandatory_reserve:
        return {'hypothetical':True,'status':'RESERVE_EXCEEDS_REDUCED_BUDGET','strategies':[]}
    data['total_budget']=cash(budget)
    data['items']=[r for r in data['items'] if r['category'] not in spec.remove_categories]
    changed=FinancialGoal.model_validate(data)
    category={p.id:p.category for p in products}
    adjusted=[]
    for offer in offers:
        percent=spec.category_price_change_percent.get(category.get(offer.product_id),Decimal(0))
        price=(offer.base_price*(1+percent/100)).quantize(Decimal('.01'))
        adjusted.append(MerchantOffer.model_validate({**offer.model_dump(mode='json'),'base_price':cash(price),
            'available':offer.available and offer.product_id not in spec.unavailable_product_ids}))
    result=evaluate(changed,products,adjusted,histories,at,hypothetical=True)
    if spec.wait_days:
        combo=next((s['plan'] for s in result['strategies'] if s['code']=='optimized'),None)
        result['wait']=waiting(changed,combo,histories,at or utc(),spec.wait_days)
    result['scenario_assumptions']=['Hypothetical base-price change only; shipping, fees, taxes and discount terms held fixed.','No market records changed. No future quotes invented.']
    return result
