"""Run reproducible demo comparisons: python -m app.finance.benchmark."""
import json
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from statistics import mean
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.entities import Base
from app.services.catalog import seed
from app.commerce.store import discover_and_persist
from app.finance.schemas import FinancialGoal,ScenarioSpec
from app.finance.engine import evaluate,simulate
from app.services.optimization import satisfies


def signature(result):
    return [(s['code'],s['status'],s['plan']['total'] if s['plan'] else None,
        [(l['offer']['id'],l['quantity']) for l in s['plan']['items']] if s['plan'] else []) for s in result['strategies']]


def compliant(goal,combo):
    if Decimal(combo['total'])>goal.spendable:return False
    for req in goal.items:
        lines=[l for l in combo['items'] if l['product']['category']==req.category]
        quantity=sum(l['quantity'] for l in lines)
        if (req.required and quantity!=req.quantity) or (not req.required and quantity not in [0,req.quantity]):return False
        if any(not satisfies({**l['product']['specifications'],'brand':l['product']['brand']},rule) for l in lines for rule in req.hard_constraints):return False
        if req.category in goal.category_limits and sum(Decimal(l['line_total']) for l in lines)>goal.category_limits[req.category]:return False
    return True


def run_benchmark():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    cases=[]
    with Session(engine) as db:
        seed(db);found=discover_and_persist(db,['laptop','monitor','keyboard','mouse','headphones'])
        at=datetime(2026,1,15,12,tzinfo=timezone.utc)
        # Explicit fixture clock; no live prices or credentials are used.
        offers=[o.model_copy(update={'retrieved_at':at,'expires_at':None}) for o in found.offers]
        for budget in [75000,100000,125000]:
            for profile in ['cost_focused','balanced','risk_averse']:
                for full in [False,True]:
                    goal=FinancialGoal(total_budget=str(budget),mandatory_reserve='10000',risk_strategy=profile,
                        category_limits={'monitor':'20000'},patience_days=14,
                        items=[{'category':c,'priority':5 if c=='laptop' else 3,
                            'hard_constraints':[{'field':'ram_gb','operator':'min','value':16}] if c=='laptop' else []}
                            for c in (['laptop','monitor','keyboard','mouse','headphones'] if full else ['laptop','monitor'])])
                    result=evaluate(goal,found.products,offers,{},at)
                    repeated=evaluate(goal,found.products,offers,{},at)
                    scenario=simulate(goal,found.products,offers,{},ScenarioSpec(category_price_change_percent={'laptop':'10'}),at)
                    rows=[{'strategy':s['code'],'status':s['status'],'simulated_total':s['plan']['total'] if s['plan'] else None,
                        'compliant':compliant(goal,s['plan']) if s['plan'] else None} for s in result['strategies']]
                    assert all(row['compliant'] is not False for row in rows)
                    assert signature(result)==signature(repeated)
                    assert all(not s['executable'] for s in scenario['strategies'])
                    cases.append({'budget':budget,'reserve':'10000.00','profile':profile,'categories':len(goal.items),
                        'comparisons':rows,'comparison_runtime_ms':result['runtime_ms'],
                        'consistent_repeat':signature(result)==signature(repeated),'price_increase_replan_feasible':scenario['status']=='AWAITING_DECISION'})
    engine.dispose()
    rows=[row for c in cases for row in c['comparisons']]
    return {'dataset':'IntentOS synthetic demo catalog; fixed fixture clock 2026-01-15T12:00:00Z; no live observations',
        'cases':cases,'summary':{'cases':len(cases),'strategy_comparisons':len(rows),'feasible_comparisons':sum(r['simulated_total'] is not None for r in rows),
        'hard_constraint_violations':sum(r['compliant'] is False for r in rows),'consistent_repeats':sum(c['consistent_repeat'] for c in cases),
        'price_increase_replans_feasible':sum(c['price_increase_replan_feasible'] for c in cases),
        'mean_comparison_runtime_ms':round(mean(c['comparison_runtime_ms'] for c in cases),3)},
        'limitations':['Costs are simulated, not real-world savings.','Runtime covers three strategy solves and assessment, and varies by machine.',
            'Immediate baseline maximizes existing utility; lowest-price baseline minimizes landed cost under identical hard constraints.',
            'Consistency uses a fixed catalog and clock. Replan feasibility is measured for a hypothetical 10% laptop base-price increase.']}


if __name__=='__main__':
    result=run_benchmark()
    root=Path(__file__).resolve().parents[3]/'docs'/'benchmarks';root.mkdir(parents=True,exist_ok=True)
    (root/'phase4.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    lines=['# Phase 4 measured demo benchmark','',result['dataset'],'', '| Budget | Profile | Categories | Immediate INR | Lowest INR | Optimized INR | Runtime ms | +10% replan |',
        '|---:|---|---:|---:|---:|---:|---:|---|']
    for case in result['cases']:
        costs=[r['simulated_total'] or r['status'] for r in case['comparisons']]
        lines.append(f"| {case['budget']} | {case['profile']} | {case['categories']} | {' | '.join(costs)} | {case['comparison_runtime_ms']} | {case['price_increase_replan_feasible']} |")
    lines+=['','Measured summary: `'+json.dumps(result['summary'])+'`','']+['- '+s for s in result['limitations']]
    (root/'phase4.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(result['summary']))
