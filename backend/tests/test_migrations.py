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
