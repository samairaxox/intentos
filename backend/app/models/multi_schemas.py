from math import isfinite
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

Category = Literal["laptop", "monitor", "keyboard", "mouse", "headphones"]

class SpecRule(BaseModel):
    field: Literal["processor_brand", "ram_gb", "storage_gb", "weight_kg", "battery_hours", "gpu", "os", "screen_inches", "refresh_hz", "resolution", "panel", "connectivity", "mechanical", "noise_cancelling", "dpi", "brand"]
    operator: Literal["eq", "min", "max"]
    value: str | float | bool

    @model_validator(mode="after")
    def numeric_comparison(self):
        if self.operator != "eq":
            try:
                if isinstance(self.value, bool) or not isfinite(float(self.value)):
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError("Minimum/maximum constraints require a finite number")
        return self

class ItemRequirement(BaseModel):
    category: Category
    quantity: int = Field(default=1, ge=1, le=10)
    required: bool = True
    priority: int = Field(default=3, ge=1, le=5)
    hard_constraints: list[SpecRule] = Field(default_factory=list, max_length=20)
    soft_preferences: list[SpecRule] = Field(default_factory=list, max_length=20)

class UtilityWeights(BaseModel):
    performance: int = Field(default=3, ge=0, le=5)
    quality: int = Field(default=3, ge=0, le=5)
    portability: int = Field(default=1, ge=0, le=5)
    battery: int = Field(default=1, ge=0, le=5)
    value: int = Field(default=3, ge=0, le=5)
    preferences: int = Field(default=3, ge=0, le=5)
    cost_savings: int = Field(default=2, ge=0, le=5)

class MultiIntent(BaseModel):
    total_budget: int | None = Field(default=None, gt=0, le=10000000)
    currency: str = "INR"
    items: list[ItemRequirement] = Field(default_factory=list, max_length=5)
    priorities: list[str] = Field(default_factory=list, max_length=20)
    weights: UtilityWeights = Field(default_factory=UtilityWeights)
    spending_preference: Literal["balanced", "quality", "savings"] = "balanced"
    use_case: str = ""
    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_categories(self):
        if len({i.category for i in self.items}) != len(self.items):
            raise ValueError("Combine quantities into one requirement per category")
        return self

    def missing(self) -> list[str]:
        details = list(self.missing_information)
        if self.total_budget is None: details.append("total budget")
        if not self.items: details.append("product categories")
        if not any(i.required for i in self.items): details.append("at least one required category")
        if self.currency != "INR": details.append("supported currency: INR")
        return list(dict.fromkeys(details))

class DemoProduct(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    category: Category
    name: str
    brand: str
    model: str
    price: int = Field(gt=0)
    currency: Literal["INR"] = "INR"
    specifications: dict[str, str | float | bool]
    performance: float = Field(ge=0, le=100)
    quality_score: float = Field(ge=0, le=100)
    available: bool
    seller: str
    seller_available: bool = True
    stock: int = Field(default=10, ge=0, le=1000)
    source_type: Literal["demo"]
    timestamp: str

class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: MultiIntent

class ReplanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: MultiIntent | None = None

class CartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str
    alternative_index: int = Field(default=0, ge=0, le=2)

class CartUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_ids: list[str] = Field(min_length=1, max_length=50)
    expected_version: int = Field(ge=1)

class BundleOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cart_id: str
    cart_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)


class PlanLine(BaseModel):
    product: DemoProduct
    quantity: int
    unit_price: int
    line_total: int
    utility: int
    reason: str

class Combination(BaseModel):
    items: list[PlanLine]
    total_cost: int
    remaining_budget: int
    utility_score: int
    category_spending: dict[str,int]
    omitted_optional: list[str]
    tradeoffs: list[str]
    solver_status: str | None = None

class PlanResult(BaseModel):
    combinations: list[Combination] = Field(default_factory=list)
    candidates: dict[str,list[DemoProduct]] = Field(default_factory=dict)
    missing_information: list[str] = Field(default_factory=list)
    status: str | None = None
    revised_plan_id: str | None = None

class PlanOut(BaseModel):
    order_ids: list[str] = Field(default_factory=list)
    id: str
    session_id: str
    parent_id: str | None
    revision: int
    status: str
    intent: MultiIntent
    result: PlanResult
    workflow: dict
    changes: list[str]

class CartOut(BaseModel):
    alternative_index: int
    id: str
    plan_id: str
    version: int
    status: str
    snapshot: Combination

class DemoChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    change: Literal["unavailable", "price_increase", "price_decrease", "seller_unavailable"]
