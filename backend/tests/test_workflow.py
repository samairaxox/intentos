import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.models.schemas import Intent, Constraint
from app.services.optimization import eligible, rank
from app.agents.workflow import build_workflow

@pytest.fixture
def catalog():
    return json.loads((Path(__file__).parents[1]/"data/laptops.json").read_text())

@pytest.fixture
def intent():
    return Intent(category="laptop",max_budget=75000,required_specifications=[Constraint(field="processor_brand",operator="eq",value="Intel"),Constraint(field="ram_gb",operator="min",value=16)],soft_preferences=[Constraint(field="weight_kg",operator="max",value=1.4)])

class FakeAI:
    def __init__(self,intent): self.intent=intent
    def parse(self,text): return self.intent
    def explain(self,recs): return {r["product"]["id"]:"Mocked explanation for automated testing" for r in recs}

class Provider:
    def __init__(self,products): self.products=products
    def discover(self): return self.products

def test_invalid_budget():
    with pytest.raises(ValidationError): Intent(category="laptop",max_budget=-1)

def test_filter_and_soft_preferences(catalog,intent):
    selected=[p for p in catalog if eligible(p,intent)]
    assert selected
    assert all(p["price"]<=75000 and p["ram_gb"]>=16 and p["processor_brand"]=="Intel" for p in selected)
    assert any(p["weight_kg"]>1.4 for p in selected)
    intent.hard_constraints=[Constraint(field="weight_kg",operator="max",value=1.4)]
    assert all(p["weight_kg"]<=1.4 for p in catalog if eligible(p,intent))

def test_rank(catalog,intent):
    selected=[p for p in catalog if eligible(p,intent)]
    result=rank(selected,intent)
    assert result==rank(list(reversed(selected)),intent)
    assert all(0<=r["score"]<=100 for r in result)
    assert result[0]["score"]>=result[-1]["score"]

def test_workflow(catalog,intent):
    result=build_workflow(FakeAI(intent),Provider(catalog)).invoke({"text":"laptop request"})
    assert result["status"]=="READY"
    assert len(result["steps"])==6
    assert len(result["recommendations"])==3

def test_impossible(catalog,intent):
    intent.max_budget=1
    result=build_workflow(FakeAI(intent),Provider(catalog)).invoke({"text":"impossible"})
    assert result["status"]=="NO_MATCH"
    assert result["recommendations"]==[]

def test_missing_details(catalog):
    result=build_workflow(FakeAI(Intent(category="laptop")),Provider(catalog)).invoke({"text":"laptop"})
    assert result["status"]=="NEEDS_DETAILS"


def test_category_and_seller_filter(catalog, intent):
    candidate=next(p for p in catalog if eligible(p,intent))
    assert not eligible({**candidate,"category":"monitor"},intent)
    assert not eligible({**candidate,"seller_available":False},intent)
    assert not eligible({**candidate,"stock":0},intent)
