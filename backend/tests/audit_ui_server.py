"""Audit-only UI harness. Run with --app-dir tests; NEVER use as a production entry point.

Explicit fixed AI fixtures exercise transport/UI/payment behavior without claiming live Gemini.
The database, optimization, offer, approval and mock payment implementations are unchanged.
"""
from app.main import app
from app.api.routes import get_ai
from app.api.commerce_routes import get_commerce_ai
from app.models.schemas import Intent,Constraint
from app.models.multi_schemas import MultiIntent
from app.commerce.schemas import CommerceIntent,PreferencePatch


def multi():
    return MultiIntent(total_budget=100000,items=[{'category':c,'priority':5 if c=='laptop' else 3} for c in ['laptop','monitor','keyboard','mouse','headphones']])


class AuditAI:
    def parse(self,text):
        return Intent(category='laptop',max_budget=75000,use_case='coding and AI development',
            required_specifications=[Constraint(field='processor_brand',operator='eq',value='Intel'),Constraint(field='ram_gb',operator='min',value=16)],
            soft_preferences=[Constraint(field='weight_kg',operator='max',value=1.4),Constraint(field='battery_hours',operator='min',value=10)])
    def parse_multi(self,text):return multi()
    def explain(self,recommendations):
        return {r['product']['id']:f"AUDIT FIXTURE (no live Gemini): {r['product']['ram_gb']} GB RAM; demo INR {r['product']['price']}; {r['product']['weight_kg']} kg." for r in recommendations}


class AuditCommerceAI:
    def parse(self,text):return CommerceIntent.model_validate(multi().model_dump())
    def patch(self,text,intent):return PreferencePatch(weights={'portability':5})
    def explain(self,combinations):return combinations


app.dependency_overrides[get_ai]=lambda:AuditAI()
app.dependency_overrides[get_commerce_ai]=lambda:AuditCommerceAI()


@app.get('/audit/fixture-status')
def fixture_status():return {'ai':'FIXED_AUDIT_FIXTURE_NOT_GEMINI','catalog':'demo','payments':'mock'}
