from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

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
    product_id: str
    amount: int
    currency: str
    status: str

    payment: PaymentOut | None = None
