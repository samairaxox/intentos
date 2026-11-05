import itertools
import json
from pathlib import Path
import pytest
from app.models.multi_schemas import MultiIntent, ItemRequirement, SpecRule, UtilityWeights
from app.services.budget_optimizer import optimize, cheapest_baseline, candidates_for, summarize

@pytest.fixture
def products():
    root=Path(__file__).parents[1]/"data"
    return json.loads((root/"laptops.json").read_text())+json.loads((root/"accessories.json").read_text())

@pytest.fixture
def setup_intent():
    return MultiIntent(total_budget=100000,items=[ItemRequirement(category=c,priority=5 if c=="laptop" else 3) for c in ["laptop","monitor","keyboard","mouse","headphones"]],weights=UtilityWeights(performance=5,value=4))

def test_full_setup_and_alternatives(products,setup_intent):
    result=optimize(setup_intent,products)
    assert result["status"]=="READY"
    assert len(result["combinations"])==3
    combos=result["combinations"]
    assert all(c["total_cost"]<=100000 for c in combos)
    assert all(len(c["category_spending"])==5 for c in combos)
    assert len({tuple((i["product"]["id"],i["quantity"]) for i in c["items"]) for c in combos})==3
    assert combos[0]["utility_score"]>=cheapest_baseline(setup_intent,products)["utility_score"]
    assert result==optimize(setup_intent,list(reversed(products)))

def test_optimizer_matches_exhaustive_search(products):
    intent=MultiIntent(total_budget=65000,items=[ItemRequirement(category="laptop"),ItemRequirement(category="monitor")])
    small=[p for p in products if p["id"] in ["demo-02","demo-03","demo-04","demo-monitor-1","demo-monitor-2"]]
    candidates=candidates_for(intent,small)
    feasible=[summarize(intent,list(pair),candidates) for pair in itertools.product(*candidates.values()) if sum(p["price"] for p in pair)<=intent.total_budget]
    expected=max(feasible,key=lambda r:(r["utility_score"],-r["total_cost"]))
    actual=optimize(intent,small)["combinations"][0]
    assert (actual["utility_score"],actual["total_cost"])==(expected["utility_score"],expected["total_cost"])

def test_infeasible_and_missing(products,setup_intent):
    setup_intent.total_budget=100
    assert optimize(setup_intent,products)["status"]=="INFEASIBLE"
    assert optimize(MultiIntent(),products)["status"]=="NEEDS_DETAILS"

def test_quantities_and_stock(products):
    intent=MultiIntent(total_budget=10000,items=[ItemRequirement(category="keyboard",quantity=3)])
    result=optimize(intent,products)["combinations"][0]
    assert sum(i["quantity"] for i in result["items"])==3
    limited=[{**p,"stock":0} for p in products]
    assert optimize(intent,limited)["status"]=="INFEASIBLE"

def test_constraints_and_optional(products):
    intent=MultiIntent(total_budget=60000,items=[ItemRequirement(category="laptop",hard_constraints=[SpecRule(field="processor_brand",operator="eq",value="Intel"),SpecRule(field="ram_gb",operator="min",value=16)]),ItemRequirement(category="headphones",required=False)])
    result=optimize(intent,products)["combinations"][0]
    for item in result["items"]:
        if item["product"]["category"]=="laptop": assert item["product"]["ram_gb"]>=16 and item["product"]["processor_brand"]=="Intel"
    intent.items[0].hard_constraints.append(SpecRule(field="ram_gb",operator="max",value=4))
    assert optimize(intent,products)["status"]=="INFEASIBLE"
