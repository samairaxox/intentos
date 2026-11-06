from collections import Counter
from decimal import Decimal
from ortools.sat.python import cp_model
from app.commerce.schemas import CommerceIntent, MerchantOffer, CanonicalProduct
from app.commerce.pricing import TotalCostService
from app.commerce.freshness import OfferFreshnessService
from app.services.optimization import satisfies


def optimize_offers(intent: CommerceIntent,products: list[CanonicalProduct],offers: list[MerchantOffer],limit=3,*,budget_minor=None,category_limits_minor=None,risk_scores=None,objective_profile="utility",as_of=None) -> dict:
    if intent.missing(): return {"status":"NEEDS_DETAILS","missing_information":intent.missing(),"combinations":[],"offers":[]}
    budget=int(intent.total_budget*100) if budget_minor is None else budget_minor
    if budget<=0:return {"status":"NO_MATCH","combinations":[],"offers":[]}
    by_id={p.id:p for p in products}
    reqs={r.category:r for r in intent.items}
    eligible=[];views=[]
    for offer in sorted(offers,key=lambda o:o.id):
        product=by_id.get(offer.product_id)
        if not product or product.category not in reqs: continue
        cost=TotalCostService().calculate(offer)
        freshness=OfferFreshnessService().inspect(offer,as_of)
        view={"offer":offer.model_dump(mode="json"),"product":product.model_dump(mode="json"),"pricing":cost,"freshness":freshness}
        views.append(view)
        if not freshness["checkout_eligible"]: continue
        if intent.allowed_merchants and offer.merchant_id not in intent.allowed_merchants: continue
        if offer.merchant_id in intent.blocked_merchants: continue
        if any(not satisfies({**product.specifications,"brand":product.brand},rule) for rule in reqs[product.category].hard_constraints): continue
        if cost["final_minor"]>budget: continue
        eligible.append(view)
    model=cp_model.CpModel();variables=[];records=[];benefits=[]
    # Utilities use Decimal, including savings/quality-price normalization; financial costs stay integer paise.
    for req in intent.items:
        peers=[v for v in eligible if v["product"]["category"]==req.category]
        best=max((Decimal(v['product']['quality_score'])/Decimal(max(1,v['pricing']['final_minor'])) for v in peers),default=Decimal(1))
        best=max(Decimal('0.0000000001'),best)
        category_vars=[]
        for view in peers:
            p=view['product'];offer=view['offer'];cost=view['pricing']['final_minor'];specs=p['specifications']
            weights=intent.weights.model_dump(exclude={'cost_savings'})
            if 'battery_hours' not in specs: weights['battery']=0
            components={'performance':Decimal(p['performance'])/100,'quality':Decimal(p['quality_score'])/100,
                'portability':1/(1+Decimal(str(specs.get('weight_kg',1)))),
                'battery':min(Decimal(1),Decimal(str(specs.get('battery_hours',0)))/24),
                'value':(Decimal(p['quality_score'])/max(1,cost))/best,
                'preferences':Decimal(sum(satisfies({**specs,'brand':p['brand']},r) for r in req.soft_preferences))/len(req.soft_preferences) if req.soft_preferences else Decimal('.5')}
            avg=sum(max(Decimal(0),min(Decimal(1),components[k]))*w for k,w in weights.items())/max(1,sum(weights.values()))
            savings=max(0,intent.weights.cost_savings+(2 if intent.spending_preference=='savings' else -1 if intent.spending_preference=='quality' else 0))
            benefit=int((10000*req.priority*avg).to_integral_value())-int((Decimal(10000*savings*cost)/budget).to_integral_value())
            if objective_profile in ["balanced","risk_averse"]:
                benefit-=int(Decimal(str((risk_scores or {}).get(offer["id"],0)))*(25 if objective_profile=="balanced" else 500))
            previous=None
            for unit in range(min(req.quantity,offer['stock'])):
                x=model.new_bool_var(f"{offer['id']}:{unit}")
                if previous is not None:model.add(x<=previous)
                previous=x;variables.append(x);records.append(view);category_vars.append(x);benefits.append(benefit)
        if req.required:model.add(sum(category_vars)==req.quantity)
        else:model.add(sum(category_vars)==req.quantity*model.new_bool_var('optional:'+req.category))
    # Duplicate listings from one merchant do not multiply its inventory; distinct merchants have distinct stock.
    groups={(r['product']['id'],r['offer']['merchant_id']) for r in records}
    for product_id,merchant_id in sorted(groups):
        relevant=[(x,r) for x,r in zip(variables,records) if r['product']['id']==product_id and r['offer']['merchant_id']==merchant_id]
        model.add(sum(x for x,_ in relevant)<=max(r['offer']['stock'] for _,r in relevant))
    cost=sum(x*r['pricing']['final_minor'] for x,r in zip(variables,records))
    utility=sum(x*b for x,b in zip(variables,benefits))
    model.add(cost<=budget)
    for category,cap in (category_limits_minor or {}).items():
        model.add(sum(x*r["pricing"]["final_minor"] for x,r in zip(variables,records) if r["product"]["category"]==category)<=cap)
    concentration=model.new_int_var(0,budget,"largest_merchant_spend")
    for merchant in {r["offer"]["merchant_id"] for r in records}:
        model.add(concentration>=sum(x*r["pricing"]["final_minor"] for x,r in zip(variables,records) if r["offer"]["merchant_id"]==merchant))
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.random_seed=0;solver.parameters.max_time_in_seconds=5
    combinations=[]
    for _ in range(min(3,limit)):
        if objective_profile=="cost_focused":
            model.minimize(cost)
        else:
            penalty=10000 if objective_profile=="risk_averse" else 1000 if objective_profile=="balanced" else 0
            model.maximize(utility*(budget+1)-cost-concentration*penalty)
        status=solver.solve(model)
        if status not in [cp_model.OPTIMAL,cp_model.FEASIBLE]:
            if not combinations:return {"status":"NO_MATCH" if status==cp_model.INFEASIBLE else "SOLVER_LIMIT","combinations":[],"offers":views}
            break
        flags=[bool(solver.value(x)) for x in variables]
        quantities=Counter(r['offer']['id'] for r,selected in zip(records,flags) if selected)
        chosen={r['offer']['id']:r for r,selected in zip(records,flags) if selected}
        lines=[];merchant_totals={};totals={k:Decimal('0.00') for k in ['base_price','shipping','fees','estimated_taxes','confirmed_discount','final_price']}
        for oid in sorted(chosen):
            view=chosen[oid];qty=quantities[oid];merchant=view['offer']['merchant_id']
            line_total=Decimal(view['pricing']['final_price'])*qty
            merchant_totals[merchant]=merchant_totals.get(merchant,Decimal('0.00'))+line_total
            for key in totals:totals[key]+=Decimal(view['pricing'][key])*qty
            lines.append({**view,'quantity':qty,'line_total':format(line_total,'.2f'),
                'reason':f"Eligible {view['product']['category']}; priority {reqs[view['product']['category']].priority}/5; confirmed landed unit cost INR {view['pricing']['final_price']}. Potential discounts excluded."})
        total=totals['final_price']
        combinations.append({'items':lines,'total':format(total,'.2f'),'remaining_budget':format(Decimal(budget)/100-total,'.2f'),
            'cost_breakdown':{key:format(value,'.2f') for key,value in totals.items()},'merchant_totals':{k:format(v,'.2f') for k,v in merchant_totals.items()},
            'budget_utilization_percent':format(total/Decimal(budget)*10000,'.2f'),'merchant_allocation':[{'merchant_id':k,'amount':format(v,'.2f'),'share_percent':format(v/total*100,'.2f') if total else '0.00'} for k,v in merchant_totals.items()],
            'utility_score':int(solver.value(utility)),'solver_status':solver.status_name(status),
            'explanation':f"Selected {sum(quantities.values())} units across {len(merchant_totals)} demo/authorized merchants within the confirmed cost budget. Shipping and fees included; unverified discounts were not used."})
        model.add_bool_or([~x if chosen else x for x,chosen in zip(variables,flags)])
    return {'status':'READY','combinations':combinations,'offers':views}
