import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.models.multi_schemas import MultiIntent, ItemRequirement, DemoProduct, SpecRule

def test_multi_intent_validation():
    intent=MultiIntent(total_budget=100000,items=[ItemRequirement(category="laptop",priority=5),ItemRequirement(category="monitor"),ItemRequirement(category="mouse",required=False)])
    assert not intent.missing()
    assert not intent.items[-1].required
    for payload in [dict(total_budget=-1),dict(items=[dict(category="laptop",quantity=0)]),dict(items=[dict(category="laptop"),dict(category="laptop")])]:
        with pytest.raises(ValidationError): MultiIntent(**payload)
    assert MultiIntent().missing()
    with pytest.raises(ValidationError): SpecRule(field="ram_gb",operator="min",value="lots")

def test_all_demo_products_have_required_metadata():
    root=Path(__file__).parents[1]/"data"
    products=json.loads((root/"laptops.json").read_text())+json.loads((root/"accessories.json").read_text())
    for product in products: DemoProduct.model_validate(product)
    assert len({p["category"] for p in products})==5
    assert len(products)==46
