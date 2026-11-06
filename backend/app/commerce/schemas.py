from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, model_validator
from app.models.multi_schemas import MultiIntent, ItemRequirement, SpecRule


def money(value):
    if isinstance(value, (float, bool)):
        raise ValueError("Money must be a decimal string or integer, never a binary float")
    try:
        number=Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid decimal money value") from exc
    if not number.is_finite() or number<0 or number>Decimal("1000000000") or number!=number.quantize(Decimal("0.01")):
        raise ValueError("Money must be finite, nonnegative and have at most two decimal places")
    return number.quantize(Decimal("0.01"))

Money=Annotated[Decimal,BeforeValidator(money)]
Source=Literal["demo","live_verified","cached","unverified"]

def utc(): return datetime.now(timezone.utc)

def aware(value: datetime):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

class Discount(BaseModel):
    label: str = Field(max_length=120)
    amount: Money
    eligibility_verified: bool = False
    eligible: bool = False
    expires_at: datetime | None = None

class CanonicalProduct(BaseModel):
    id: str
    category: str
    brand: str
    model: str
    name: str
    specifications: dict
    performance: int = Field(ge=0,le=100)
    quality_score: int = Field(ge=0,le=100)

class MerchantOffer(BaseModel):
    id: str
    product_id: str
    merchant_id: str
    merchant_name: str
    base_price: Money
    shipping: Money = Decimal("0.00")
    fees: Money = Decimal("0.00")
    estimated_taxes: Money = Decimal("0.00")
    taxes_supported: bool = False
    currency: Literal["INR"] = "INR"
    discounts: list[Discount] = Field(default_factory=list,max_length=20)
    stock: int = Field(ge=0,le=1000)
    available: bool = True
    merchant_available: bool = True
    offer_url: str | None = None
    source_type: Source = "unverified"
    verification_status: Literal["demo","verified","unverified"] = "unverified"
    retrieved_at: datetime
    expires_at: datetime | None = None
    provider_id: str

    @model_validator(mode="after")
    def validate_provenance(self):
        if self.source_type=="demo" and self.verification_status!="demo":
            raise ValueError("Demo offers must be labelled demo")
        if self.source_type=="live_verified" and self.verification_status!="verified":
            raise ValueError("Live offers require verified provenance")
        if self.offer_url and not self.offer_url.startswith("https://"):
            raise ValueError("External offer URLs must use HTTPS")
        return self

class CommerceIntent(MultiIntent):
    allowed_merchants: list[str] = Field(default_factory=list,max_length=20)
    blocked_merchants: list[str] = Field(default_factory=list,max_length=20)

class SessionStart(BaseModel):
    model_config=ConfigDict(extra="forbid")
    text: str | None = Field(default=None,min_length=10,max_length=4000)
    intent: CommerceIntent | None = None

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.text is None)==(self.intent is None): raise ValueError("Provide exactly one of text or structured intent")
        return self

class ItemPatch(BaseModel):
    model_config=ConfigDict(extra="forbid")
    category: Literal["laptop","monitor","keyboard","mouse","headphones"]
    quantity: int | None = Field(default=None,ge=1,le=10)
    priority: int | None = Field(default=None,ge=1,le=5)
    required: bool | None = None
    hard_constraints: list[SpecRule] | None = None
    soft_preferences: list[SpecRule] | None = None
    remove: bool = False

class PreferencePatch(BaseModel):
    model_config=ConfigDict(extra="forbid")
    total_budget: int | None = Field(default=None,gt=0,le=10000000)
    items: list[ItemPatch] = Field(default_factory=list,max_length=5)
    spending_preference: Literal["balanced","quality","savings"] | None = None
    allowed_merchants: list[str] | None = None
    blocked_merchants: list[str] | None = None

class SessionUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    text: str | None = Field(default=None,min_length=3,max_length=2000)
    patch: PreferencePatch | None = None

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.text is None)==(self.patch is None): raise ValueError("Provide exactly one of text or explicit patch")
        return self

class PurchaseCreate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    plan_id: str
    alternative_index: int = Field(default=0,ge=0,le=2)
    idempotency_key: str = Field(min_length=8,max_length=100)

Simulation=Literal["success","failure","timeout_captured","timeout_unknown","checkout_failure"]
class ExecuteRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=8,max_length=100)
    simulations: dict[str,Simulation] = Field(default_factory=dict)

class RetryRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=8,max_length=100)
    simulation: Simulation = "success"

class OfferChange(BaseModel):
    model_config=ConfigDict(extra="forbid")
    offer_id: str
    change: Literal["price_increase","price_decrease","out_of_stock","merchant_unavailable","expired"]

class DemoResolution(BaseModel):
    model_config=ConfigDict(extra="forbid")
    outcome: Literal["CAPTURED","FAILED"]
