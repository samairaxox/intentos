"""Additive Phase 3 commerce records. Legacy products, orders and payments remain intact."""
from sqlalchemy import String, Integer, JSON, ForeignKey, DateTime, Numeric, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.entities import Base, uid, now
from datetime import datetime
from decimal import Decimal

class Merchant(Base):
    __tablename__="merchants"
    id: Mapped[str]=mapped_column(String(100),primary_key=True)
    name: Mapped[str]=mapped_column(String(200))
    available: Mapped[bool]=mapped_column(Boolean,default=True)
    source_type: Mapped[str]=mapped_column(String(32))

class ProductOffer(Base):
    __tablename__="product_offers"
    id: Mapped[str]=mapped_column(String(160),primary_key=True)
    product_id: Mapped[str]=mapped_column(ForeignKey("products.id"))
    merchant_id: Mapped[str]=mapped_column(ForeignKey("merchants.id"))
    data: Mapped[dict]=mapped_column(JSON)
    revision: Mapped[int]=mapped_column(Integer,default=1)

class CommerceSession(Base):
    __tablename__="commerce_sessions"
    id: Mapped[str]=mapped_column(ForeignKey("purchase_sessions.id"),primary_key=True)
    intent: Mapped[dict]=mapped_column(JSON)
    conversation: Mapped[list]=mapped_column(JSON,default=list)
    version: Mapped[int]=mapped_column(Integer,default=1)
    latest_plan_id: Mapped[str | None]=mapped_column(String(36),nullable=True)

class CommercePlan(Base):
    __tablename__="commerce_plans"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    session_id: Mapped[str]=mapped_column(ForeignKey("commerce_sessions.id"))
    parent_id: Mapped[str | None]=mapped_column(ForeignKey("commerce_plans.id"),nullable=True)
    version: Mapped[int]=mapped_column(Integer)
    status: Mapped[str]=mapped_column(String(40))
    intent: Mapped[dict]=mapped_column(JSON)
    result: Mapped[dict]=mapped_column(JSON,default=dict)
    workflow: Mapped[dict]=mapped_column(JSON,default=dict)
    changes: Mapped[list]=mapped_column(JSON,default=list)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint("session_id","version",name="uq_commerce_plan_version"),)

class OfferSnapshot(Base):
    __tablename__="offer_snapshots"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    plan_id: Mapped[str]=mapped_column(ForeignKey("commerce_plans.id"))
    offer_id: Mapped[str]=mapped_column(ForeignKey("product_offers.id"))
    data: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class CommercePurchase(Base):
    __tablename__="commerce_purchases"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    plan_id: Mapped[str]=mapped_column(ForeignKey("commerce_plans.id"))
    snapshot: Mapped[dict]=mapped_column(JSON)
    amount: Mapped[Decimal]=mapped_column(Numeric(14,2))
    status: Mapped[str]=mapped_column(String(40),default="PENDING_APPROVAL")
    idempotency_key: Mapped[str]=mapped_column(String(100),unique=True)
    alternative_index: Mapped[int]=mapped_column(Integer)
    execution_key: Mapped[str | None]=mapped_column(String(100),nullable=True,unique=True)
    execution_modes: Mapped[dict]=mapped_column(JSON,default=dict)
    approved_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class MerchantSuborder(Base):
    __tablename__="merchant_suborders"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    purchase_id: Mapped[str]=mapped_column(ForeignKey("commerce_purchases.id"))
    merchant_id: Mapped[str]=mapped_column(ForeignKey("merchants.id"))
    amount: Mapped[Decimal]=mapped_column(Numeric(14,2))
    status: Mapped[str]=mapped_column(String(40),default="PENDING_APPROVAL")
    items: Mapped[list]=mapped_column(JSON)
    __table_args__=(UniqueConstraint("purchase_id","merchant_id",name="uq_purchase_merchant"),)

class PaymentIntentRecord(Base):
    __tablename__="payment_intents"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    suborder_id: Mapped[str]=mapped_column(ForeignKey("merchant_suborders.id"),unique=True)
    amount: Mapped[Decimal]=mapped_column(Numeric(14,2))
    currency: Mapped[str]=mapped_column(String(3),default="INR")
    provider: Mapped[str]=mapped_column(String(40),default="mock")
    status: Mapped[str]=mapped_column(String(40),default="REQUIRES_APPROVAL")

class PaymentAttempt(Base):
    __tablename__="payment_attempts"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    intent_id: Mapped[str]=mapped_column(ForeignKey("payment_intents.id"))
    idempotency_key: Mapped[str]=mapped_column(String(160),unique=True)
    status: Mapped[str]=mapped_column(String(40))
    simulation: Mapped[str]=mapped_column(String(40))
    attempt_number: Mapped[int]=mapped_column(Integer)
    retry_after: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint("intent_id","attempt_number",name="uq_intent_attempt_number"),)

class MockProviderReceipt(Base):
    __tablename__="mock_provider_receipts"
    idempotency_key: Mapped[str]=mapped_column(String(160),primary_key=True)
    amount: Mapped[Decimal]=mapped_column(Numeric(14,2))
    outcome: Mapped[str]=mapped_column(String(40))
    reference: Mapped[str]=mapped_column(String(36),default=uid)

class ReconciliationRecord(Base):
    __tablename__="payment_reconciliations"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    attempt_id: Mapped[str]=mapped_column(ForeignKey("payment_attempts.id"))
    outcome: Mapped[str]=mapped_column(String(40))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class WorkflowTrace(Base):
    __tablename__="workflow_traces"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    workflow_id: Mapped[str]=mapped_column(String(36),index=True)
    session_id: Mapped[str]=mapped_column(ForeignKey("commerce_sessions.id"))
    node: Mapped[str]=mapped_column(String(100))
    status: Mapped[str]=mapped_column(String(40))
    details: Mapped[dict]=mapped_column(JSON,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
