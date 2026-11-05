import json
from pathlib import Path
import pytest
from app.evaluation import evaluate_one

SCENARIOS=json.loads((Path(__file__).parents[1]/"evaluations/scenarios.json").read_text())

@pytest.mark.parametrize("scenario",SCENARIOS,ids=[s["id"] for s in SCENARIOS])
def test_reproducible_purchasing_scenario(scenario):
    observed=evaluate_one(scenario)
    assert observed["passed"],observed
    assert observed["budget_compliant"]==observed["plan_checks"]
    assert observed["hard_constraints_satisfied"]==observed["plan_checks"]
