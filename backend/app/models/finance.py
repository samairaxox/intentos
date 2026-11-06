from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, JSON, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.entities import Base, uid, now


class PriceObservation(Base):
    __tablename__ = 'price_observations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    quote_key: Mapped[str] = mapped_column(String(64), unique=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'))
    offer_id: Mapped[str] = mapped_column(ForeignKey('product_offers.id'))
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default='INR')
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    source: Mapped[str] = mapped_column(String(32))
    verification: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(32))


class FinancialDecision(Base):
    __tablename__ = 'financial_decisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey('commerce_sessions.id'), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('financial_decisions.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default='PLANNING')
    goal: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    workflow: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FinancialPlanLink(Base):
    __tablename__ = 'financial_plan_links'
    plan_id: Mapped[str] = mapped_column(ForeignKey('commerce_plans.id'), primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey('financial_decisions.id'))
    strategy: Mapped[str] = mapped_column(String(40))


class ScenarioSimulation(Base):
    __tablename__ = 'scenario_simulations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    decision_id: Mapped[str] = mapped_column(ForeignKey('financial_decisions.id'))
    parameters: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
