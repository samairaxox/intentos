"""Reproducible commerce evaluation; Gemini is mocked, optimization/payments are real code.
Run from backend: python -m app.evaluation
"""
import argparse
import json
import logging
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from fastapi.testclient import TestClient
from secrets import token_urlsafe
from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.api.routes import get_ai
from app.db.session import get_db
from app.models.entities import Base
from app.models.multi_schemas import MultiIntent
from app.services.catalog import seed, LocalCatalogProvider
from app.services.budget_optimizer import cheapest_baseline, matches


def evaluate_one(scenario: dict) -> dict:
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    with factory() as db:
        seed(db)
        products=LocalCatalogProvider(db).discover()
    intent=MultiIntent.model_validate(scenario["intent"])
    class FixtureAI:
        def parse_multi(self,text): return intent
    def database():
        with factory() as db: yield db
    previous=dict(app.dependency_overrides)
    app.dependency_overrides[get_db]=database
    app.dependency_overrides[get_ai]=lambda:FixtureAI()
    started=perf_counter()
    result={"id":scenario["id"],"kind":scenario["kind"],"passed":False,"plan_checks":0,"budget_compliant":0,"hard_constraints_satisfied":0,"replanned":False,"payment_verified":False}
    credential=token_urlsafe(32)
    previous_auth=(settings.auth_tokens,settings.auth_admins)
    settings.auth_tokens={credential:'evaluation-fixture'};settings.auth_admins=['evaluation-fixture']
    try:
        with TestClient(app,headers={'Authorization':'Bearer '+credential}) as client:
            def post(path,body,expected=200):
                response=client.post('/api/v1'+path,json=body)
                assert response.status_code==expected,(path,response.status_code,response.text)
                return response.json()
            def check_plan(plan):
                parsed=MultiIntent.model_validate(plan["intent"])
                combo=plan["result"]["combinations"][0]
                result["plan_checks"]+=1
                assert combo["total_cost"]<=parsed.total_budget
                assert combo["remaining_budget"]==parsed.total_budget-combo["total_cost"]
                result["budget_compliant"]+=1
                reqs={r.category:r for r in parsed.items}
                counts=Counter()
                for line in combo["items"]:
                    assert matches(line["product"],reqs[line["product"]["category"]],parsed)
                    assert line["quantity"]<=line["product"]["stock"]
                    counts[line["product"]["category"]]+=line["quantity"]
                for req in parsed.items: assert counts[req.category] in ([req.quantity] if req.required else [0,req.quantity])
                result["hard_constraints_satisfied"]+=1
                return combo
            plan=post('/multi/analyze',{'text':scenario['request']},201)
            assert plan['status']==scenario['expected']
            result['feasibility']=plan['status']
            if plan['status']!='READY':
                assert not plan['result']['combinations']
            else:
                combo=check_plan(plan)
                baseline=cheapest_baseline(intent,products)
                result.update(optimized_utility=combo['utility_score'],baseline_utility=baseline.get('utility_score'),optimized_cost=combo['total_cost'],baseline_cost=baseline.get('total_cost'),solver_status=combo.get('solver_status'))
                if baseline['status']=='READY' and combo['solver_status']=='OPTIMAL': assert combo['utility_score']>=baseline['utility_score']
                def order_for(selected_plan):
                    cart=post('/carts',{'plan_id':selected_plan['id']},201)
                    order=post('/multi/orders',{'cart_id':cart['id'],'cart_version':cart['version'],'idempotency_key':scenario['id']+'-'+selected_plan['id']},201)
                    return cart,order,'/orders/'+order['id']
                cart,order,path=order_for(plan)
                post(path+'/pay',{'idempotency_key':'unapproved-'+order['id']},409)
                post(path+'/approve',{'approved':True})
                kind=scenario['kind']
                replan_kinds=['unavailable','price_increase','price_decrease','seller_unavailable','budget_change','preference_change']
                if kind in replan_kinds:
                    if kind in ['budget_change','preference_change']:
                        changed=intent.model_dump()
                        if kind=='budget_change': changed['total_budget']=80000+scenario['variant']*5000
                        else: changed['spending_preference']='savings';changed['weights']['cost_savings']=5
                        revised=post('/plans/'+plan['id']+'/replan',{'intent':changed},201)
                    else:
                        post('/plans/'+plan['id']+'/simulate-change',{'product_id':cart['snapshot']['items'][0]['product']['id'],'change':kind})
                        blocked=post(path+'/pay',{'idempotency_key':'stale-'+order['id']},409)
                        revised=client.get('/api/v1/plans/'+blocked['detail']['revised_plan_id']).json()
                    assert client.get('/api/v1'+path).json()['status']=='CANCELLED'
                    assert revised['parent_id']==plan['id'] and revised['revision']==2
                    check_plan(revised)
                    result['replanned']=True
                    cart,order,path=order_for(revised)
                    assert order['status']=='PENDING_APPROVAL'
                    post(path+'/pay',{'idempotency_key':'unapproved-'+order['id']},409)
                    post(path+'/approve',{'approved':True})
                body={'idempotency_key':'payment-'+order['id'],'simulate_failure':kind=='payment_failure'}
                payment=post(path+'/pay',body)
                expected='PAYMENT_FAILED' if body['simulate_failure'] else 'PAID'
                assert payment['status']==expected
                assert post(path+'/pay',body)['id']==payment['id']
                saved=client.get('/api/v1'+path).json()
                assert saved['status']==expected and saved['payment']['id']==payment['id']
                result['payment_verified']=True
                result['payment_state']=expected
            result['passed']=True
    except Exception as exc:
        result['error']=str(exc)
    finally:
        settings.auth_tokens,settings.auth_admins=previous_auth
        result['elapsed_ms']=round((perf_counter()-started)*1000,3)
        app.dependency_overrides.clear();app.dependency_overrides.update(previous)
        engine.dispose()
    return result


def run(output: Path) -> dict:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    scenarios=json.loads((Path(__file__).parents[1]/'evaluations/scenarios.json').read_text())
    rows=[evaluate_one(scenario) for scenario in scenarios]
    checks=sum(r['plan_checks'] for r in rows)
    replans=[r for r in rows if r['kind'] in ['unavailable','price_increase','price_decrease','seller_unavailable','budget_change','preference_change']]
    payments=[r for r in rows if r.get('feasibility')=='READY']
    comparable=[r for r in rows if r.get('baseline_utility') is not None]
    summary={
        'scenario_count':len(rows),'passed':sum(r['passed'] for r in rows),
        'budget_compliance_rate':sum(r['budget_compliant'] for r in rows)/checks if checks else None,
        'hard_constraint_satisfaction_rate':sum(r['hard_constraints_satisfied'] for r in rows)/checks if checks else None,
        'plan_checks':checks,'feasibility_counts':dict(Counter(r.get('feasibility','ERROR') for r in rows)),
        'replanning_success_rate':sum(r['replanned'] for r in replans)/len(replans),
        'payment_workflow_reliability':sum(r['payment_verified'] for r in payments)/len(payments),
        'mean_optimized_utility':statistics.mean(r['optimized_utility'] for r in comparable),
        'mean_baseline_utility':statistics.mean(r['baseline_utility'] for r in comparable),
        'utility_comparisons':len(comparable),
        'mean_execution_ms':statistics.mean(r['elapsed_ms'] for r in rows),
        'p95_execution_ms':sorted(r['elapsed_ms'] for r in rows)[int(.95*(len(rows)-1))],
    }
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Mocked Gemini; real LangGraph, CP-SAT, API, SQLite persistence and mock payment execution. No live model-quality, PostgreSQL concurrency or real-money claims. Timing excludes database fixture creation and includes local API flow; not production latency.','summary':summary,'scenarios':rows}
    output.mkdir(parents=True,exist_ok=True)
    (output/'phase2.json').write_text(json.dumps(report,indent=2))
    lines=['# Phase 2 evaluation results','',report['scope'],'',f"Generated (UTC): {report['generated_at_utc']}",'','| Metric | Observed value |','| --- | --- |']
    lines += [f'| {key} | {value} |' for key,value in summary.items()]
    lines += ['','## Baseline','', 'The baseline independently selects the cheapest eligible available units for each required category, omits optional items, and reports infeasible when that cart exceeds budget. Both systems use the same integer utility function and original catalog snapshot. Utilities are synthetic heuristic units; they are not real-world savings or model accuracy.','', '| Scenario | Passed | Status | Utility / baseline | Time (ms) |','| --- | --- | --- | --- | --- |']
    lines += [f"| {r['id']} | {r['passed']} | {r.get('feasibility','ERROR')} | {r.get('optimized_utility','-')} / {r.get('baseline_utility','-')} | {r['elapsed_ms']} |" for r in rows]
    (output/'phase2.md').write_text('\n'.join(lines)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path(__file__).parents[2]/'docs/benchmarks')
    args=parser.parse_args()
    report=run(args.output)
    print(json.dumps(report['summary'],indent=2))
    raise SystemExit(0 if report['summary']['passed']==report['summary']['scenario_count'] else 1)
