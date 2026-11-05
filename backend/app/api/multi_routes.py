from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.routes import get_ai
from app.db.session import get_db
from app.models.entities import Product
from app.models.schemas import AnalyzeRequest, OrderOut
from app.models.multi_schemas import (OptimizeRequest, ReplanRequest, CartRequest, CartUpdate, BundleOrderRequest,
                                     PlanOut, CartOut, DemoProduct, DemoChange, PlanResult, Combination)
from app.services import plans
from app.services.budget_optimizer import optimize
from app.services.bundle_checkout import create_bundle_order
from app.services.catalog import LocalCatalogProvider
from app.services.gemini import AIUnavailable

router=APIRouter(prefix="/api/v1")

@router.get("/catalog",response_model=list[DemoProduct])
def catalog(category: str | None = None, db: Session = Depends(get_db)):
    return LocalCatalogProvider(db).discover([category] if category else None)

@router.post("/multi/analyze",response_model=PlanOut,status_code=201)
def analyze(request: AnalyzeRequest, db: Session = Depends(get_db), ai=Depends(get_ai)):
    try:
        plan=plans.generate(db,text=request.text,ai=ai)
    except AIUnavailable as exc:
        raise HTTPException(503,str(exc)) from exc
    db.commit()
    return plans.present(plan)

@router.post("/plans",response_model=PlanOut,status_code=201)
def generate(request: OptimizeRequest, db: Session = Depends(get_db)):
    plan=plans.generate(db,intent=request.intent)
    db.commit()
    return plans.present(plan)

@router.post("/optimization",response_model=PlanResult)
def budget_optimization(request: OptimizeRequest, db: Session = Depends(get_db)):
    return optimize(request.intent,LocalCatalogProvider(db).discover())

@router.get("/plans/{plan_id}",response_model=PlanOut)
def read(plan_id: str, db: Session = Depends(get_db)):
    return plans.present(plans.get_plan(db,plan_id))

@router.get("/plans/{plan_id}/alternatives",response_model=list[Combination])
def alternatives(plan_id: str, db: Session = Depends(get_db)):
    plan=plans.get_plan(db,plan_id)
    if plan.status!="READY": raise HTTPException(409,{"message":"Plan is not ready","revised_plan_id":plan.result.get("revised_plan_id")})
    return plan.result["combinations"]

@router.post("/plans/{plan_id}/validate")
def validate(plan_id: str, db: Session = Depends(get_db)) -> dict:
    return plans.validate_plan(db,plan_id)

@router.post("/plans/{plan_id}/replan",response_model=PlanOut,status_code=201)
def replan(plan_id: str, request: ReplanRequest, db: Session = Depends(get_db)):
    return plans.present(plans.replan(db,plans.get_plan(db,plan_id),intent=request.intent))

@router.post("/plans/{plan_id}/simulate-change")
def simulate(plan_id: str, request: DemoChange, db: Session = Depends(get_db)) -> dict:
    plan=plans.get_plan(db,plan_id)
    if request.product_id not in [line["product"]["id"] for combo in plan.result.get("combinations",[]) for line in combo["items"]]:
        raise HTTPException(422,"Select a product from this demo plan")
    row=db.scalar(select(Product).where(Product.id==request.product_id).with_for_update())
    if not row or row.data.get("source_type")!="demo": raise HTTPException(422,"Only demonstration products can be changed")
    updates={"unavailable":{"available":False},"seller_unavailable":{"seller_available":False},
             "price_increase":{"price":row.data["price"]+1000},"price_decrease":{"price":max(1,row.data["price"]-1000)}}
    row.data={**row.data,**updates[request.change]}
    db.commit()
    return {"product_id":row.id,"change":request.change,"message":"Demo catalog changed. Validate or checkout to trigger autonomous replanning."}

@router.post("/carts",response_model=CartOut,status_code=201)
def create_cart(request: CartRequest, db: Session = Depends(get_db)):
    return plans.present_cart(plans.create_cart(db,request))

@router.get("/carts/{cart_id}",response_model=CartOut)
def cart(cart_id: str, db: Session = Depends(get_db)):
    return plans.present_cart(plans.get_cart(db,cart_id))

@router.post("/carts/{cart_id}/items",response_model=CartOut)
def edit_cart(cart_id: str, request: CartUpdate, db: Session = Depends(get_db)):
    return plans.present_cart(plans.update_cart(db,cart_id,request))

@router.post("/multi/orders",response_model=OrderOut,status_code=201)
def create_order(request: BundleOrderRequest, db: Session = Depends(get_db)):
    return create_bundle_order(db,request)
