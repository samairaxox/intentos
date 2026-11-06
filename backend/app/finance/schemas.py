from datetime import date
from decimal import Decimal, ROUND_CEILING
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.commerce.schemas import CommerceIntent, Money
from app.models.multi_schemas import Category


class FinancialGoal(CommerceIntent):
    total_budget: Money | None = None
    mandatory_reserve: Money = Decimal('0.00')
    category_limits: dict[Category, Money] = Field(default_factory=dict)
    risk_strategy: Literal['cost_focused','balanced','risk_averse'] = 'balanced'
    patience_days: int = Field(default=0, ge=0, le=365)
    deadline: date | None = None
    opportunity_cost_per_day: Money = Decimal('0.00')
    target_total: Money | None = None
    history_mode: Literal['recorded','synthetic_demo'] = 'recorded'

    @model_validator(mode='after')
    def budget_valid(self):
        if self.total_budget is not None:
            if self.total_budget>10000000: raise ValueError('Budget exceeds supported INR 10000000')
            if self.mandatory_reserve>self.total_budget: raise ValueError('Reserve exceeds available budget')
        return self

    @property
    def spendable(self):
        return (self.total_budget or Decimal(0))-self.mandatory_reserve

    def commerce_intent(self):
        data=self.model_dump(mode='json',include=set(CommerceIntent.model_fields))
        data['total_budget']=max(1,int(self.spendable.to_integral_value(rounding=ROUND_CEILING)))
        return CommerceIntent.model_validate(data)


class DecisionStart(BaseModel):
    text: str | None = Field(default=None,min_length=3,max_length=5000)
    goal: FinancialGoal | None = None

    @model_validator(mode='after')
    def exactly_one(self):
        if (self.text is None)==(self.goal is None): raise ValueError('Supply text or goal')
        return self


class DecisionUpdate(BaseModel):
    goal: FinancialGoal


class ScenarioSpec(BaseModel):
    category_price_change_percent: dict[Category,Decimal] = Field(default_factory=dict)
    budget_reduction: Money = Decimal('0.00')
    remove_categories: list[Category] = Field(default_factory=list)
    unavailable_product_ids: list[str] = Field(default_factory=list,max_length=100)
    wait_days: int = Field(default=0,ge=0,le=365)

    @model_validator(mode='after')
    def percentages(self):
        if any(not v.is_finite() or v < -100 or v > 500 for v in self.category_price_change_percent.values()):
            raise ValueError('Price changes must be finite and between -100 and 500 percent')
        return self


class StrategySelection(BaseModel):
    strategy: Literal['optimized','immediate','lowest_price','essentials_now']
    idempotency_key: str = Field(min_length=8,max_length=100)
