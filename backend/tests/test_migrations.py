from pathlib import Path
from datetime import datetime
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, MetaData, Table, select
from app.core.config import settings


def test_phase1_data_survives_upgrade_and_empty_downgrade(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,"database_url",f"sqlite:///{tmp_path / 'migration.db'}")
    root=Path(__file__).parents[1]
    config=Config(str(root/"alembic.ini"))
    config.set_main_option("script_location",str(root/"migrations"))
    command.upgrade(config,"0001")
    engine=create_engine(settings.database_url)
    with engine.begin() as conn:
        metadata=MetaData()
        products=Table("products",metadata,autoload_with=conn)
        sessions=Table("purchase_sessions",metadata,autoload_with=conn)
        orders=Table("orders",metadata,autoload_with=conn)
        conn.execute(products.insert().values(id="legacy-product",data={"category":"laptop"}))
        conn.execute(sessions.insert().values(id="legacy-session",request="legacy request",result={},created_at=datetime.now()))
        conn.execute(orders.insert().values(id="legacy-order",session_id="legacy-session",product_id="legacy-product",amount=100,currency="INR",status="PAID",idempotency_key="legacy-key",created_at=datetime.now()))
    command.upgrade(config,"head")
    with engine.connect() as conn:
        orders=Table("orders",MetaData(),autoload_with=conn)
        legacy=conn.execute(select(orders)).mappings().one()
        assert legacy["status"]=="PAID" and legacy["product_id"]=="legacy-product"
        assert legacy["cart_id"] is None
    command.downgrade(config,"0001")
    command.upgrade(config,"head")
    engine.dispose()


def test_financial_evidence_survives_upgrade_and_blocks_destructive_downgrade(tmp_path,monkeypatch):
    import pytest
    from sqlalchemy.orm import Session
    from app.services.catalog import seed
    from app.commerce.store import discover_and_persist
    from app.models.finance import PriceObservation
    from app.models.entities import Base
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    monkeypatch.setattr(settings,'database_url',f"sqlite:///{tmp_path / 'finance-migration.db'}")
    root=Path(__file__).parents[1]
    config=Config(str(root/'alembic.ini'));config.set_main_option('script_location',str(root/'migrations'))
    command.upgrade(config,'0005')
    engine=create_engine(settings.database_url)
    with Session(engine) as db:
        seed(db);discover_and_persist(db,['laptop']);db.commit()
        count=len(list(db.scalars(select(PriceObservation))))
        assert count>0
    command.upgrade(config,'head')
    with engine.connect() as conn:
        diffs=compare_metadata(MigrationContext.configure(conn),Base.metadata)
        financial_tables={'price_observations','financial_decisions','financial_plan_links','scenario_simulations'}
        assert not [d for d in diffs if any(name in str(d) for name in financial_tables)],diffs
    with pytest.raises(RuntimeError,match='Cannot discard recorded financial'):
        command.downgrade(config,'0004')
    command.upgrade(config,'head')
    with Session(engine) as db: assert len(list(db.scalars(select(PriceObservation))))==count
    engine.dispose()
