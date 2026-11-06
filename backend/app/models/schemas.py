from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

class Constraint(BaseModel):
    field: Literal["processor_brand", "ram_gb", "weight_kg", "storage_gb", "battery_hours", "gpu", "os"]
    operator: Literal["eq", "min", "max"]
    value: str | float

class Intent(BaseModel):
    category: str
    max_budget: int | None = Field(default=None, gt=0)
    currency: str = "INR"
    required_specifications: list[Constraint] = Field(default_factory=list)
    preferred_specifications: list[Constraint] = Field(default_factory=list)
    use_case: str = ""
    hard_constraints: list[Constraint] = Field(default_factory=list)
    soft_preferences: list[Constraint] = Field(default_factory=list)
    missing_essential_details: list[str] = Field(default_factory=list)

class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=10, max_length=4000)

class CreateOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    product_id: str
    idempotency_key: str = Field(min_length=8, max_length=100)

class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: Literal[True]

    @field_validator("approved", mode="before")
    @classmethod
    def explicit_boolean(cls, value):
        if value is not True:
            raise ValueError("Approval must be the JSON boolean true")
        return value

class PayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=8, max_length=100)
    simulate_failure: bool = False

class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    order_id: str
    amount: int
    status: str

class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    session_id: str
    product_id: str | None
    cart_id: str | None = None
    items: list[dict] = Field(default_factory=list)
    amount: int
    currency: str
    status: str

    payment: PaymentOut | None = None


class CatalogProduct(BaseModel):
    id: str
    name: str
    category: str
    price: int
    currency: str
    processor_brand: str
    processor: str
    ram_gb: int
    storage_gb: int
    weight_kg: float
    battery_hours: float
    gpu: str
    os: str
    performance: float
    seller: str
    available: bool
    source_type: Literal["demo"]
    timestamp: str

class Recommendation(BaseModel):
    product: CatalogProduct
    score: float
    breakdown: dict[str, float]
    tradeoffs: list[str]
    explanation: str

class PurchaseOut(BaseModel):
    id: str
    text: str
    status: Literal["READY", "NO_MATCH", "NEEDS_DETAILS", "PLANNING", "INTERRUPTED"]
    intent: Intent
    steps: list[str]
    recommendations: list[Recommendation] = Field(default_factory=list)

class EventOut(BaseModel):
    id: str
    event: str
    created_at: str
