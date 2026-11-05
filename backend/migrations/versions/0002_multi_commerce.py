"""Persist multi-product plans, carts and item snapshots while retaining legacy orders."""
from alembic import op
import sqlalchemy as sa
revision="0002"
down_revision="0001"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("purchase_plans",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("session_id",sa.String(36),sa.ForeignKey("purchase_sessions.id"),nullable=False),
        sa.Column("parent_id",sa.String(36),sa.ForeignKey("purchase_plans.id"),nullable=True),
        sa.Column("status",sa.String(32),nullable=False),sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("intent",sa.JSON(),nullable=False),sa.Column("result",sa.JSON(),nullable=False),
        sa.Column("workflow",sa.JSON(),nullable=False),sa.Column("changes",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("carts",sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("plan_id",sa.String(36),sa.ForeignKey("purchase_plans.id"),nullable=False),
        sa.Column("alternative_index",sa.Integer(),nullable=False),sa.Column("snapshot",sa.JSON(),nullable=False),
        sa.Column("version",sa.Integer(),nullable=False),sa.Column("status",sa.String(32),nullable=False))
    with op.batch_alter_table("orders") as batch:
        batch.alter_column("product_id",existing_type=sa.String(64),nullable=True)
        batch.add_column(sa.Column("cart_id",sa.String(36),nullable=True))
        batch.create_foreign_key("fk_orders_cart_id","carts",["cart_id"],["id"])
        batch.create_unique_constraint("uq_orders_cart_id",["cart_id"])
    op.create_table("order_items",sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("order_id",sa.String(36),sa.ForeignKey("orders.id"),nullable=False),
        sa.Column("product_id",sa.String(64),sa.ForeignKey("products.id"),nullable=False),
        sa.Column("quantity",sa.Integer(),nullable=False),sa.Column("unit_price",sa.Integer(),nullable=False),
        sa.Column("seller",sa.String(200),nullable=False),sa.Column("snapshot",sa.JSON(),nullable=False))

def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM orders WHERE cart_id IS NOT NULL")).scalar():
        raise RuntimeError("Cannot downgrade while multi-item orders exist; preserve financial history")
    op.drop_table("order_items")
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("uq_orders_cart_id",type_="unique")
        batch.drop_constraint("fk_orders_cart_id",type_="foreignkey")
        batch.drop_column("cart_id")
        batch.alter_column("product_id",existing_type=sa.String(64),nullable=False)
    op.drop_table("carts");op.drop_table("purchase_plans")
