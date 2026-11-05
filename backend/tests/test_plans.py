from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.entities import Base, Product
from app.models.multi_schemas import MultiIntent, ItemRequirement, CartRequest
from app.services.catalog import seed
from app.services import plans


def test_persisted_workflow_replanning_and_checkout():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine,expire_on_commit=False)() as db:
        seed(db)
        intent=MultiIntent(total_budget=100000,items=[ItemRequirement(category=c) for c in ["laptop","monitor","keyboard","mouse","headphones"]])
        plan=plans.generate(db,intent=intent);db.commit()
        assert plan.status=="READY" and plan.workflow["awaiting_selection"]
        cart=plans.create_cart(db,CartRequest(plan_id=plan.id))
        assert "Prepare Checkout" in plan.workflow["steps"]
        product=db.get(Product,cart.snapshot["items"][0]["product"]["id"])
        product.data={**product.data,"available":False};db.commit()
        checked=plans.validate_plan(db,plan.id)
        assert checked["valid"] is False
        revised=plans.get_plan(db,checked["revised_plan_id"])
        assert revised.parent_id==plan.id and revised.revision==2
        assert product.id not in [i["product"]["id"] for i in revised.result["combinations"][0]["items"]]
        assert plans.get_cart(db,cart.id).status=="STALE"
        assert revised.changes
        assert plans.replan(db,plan).id==revised.id
    engine.dispose()
