from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    """Frozen initial schema, independent of future ORM changes."""
    op.create_table('products',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('purchase_sessions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('request', sa.String(length=4000), nullable=False),
    sa.Column('result', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('orders',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('product_id', sa.String(length=64), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['purchase_sessions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_table('audit_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('order_id', sa.String(length=36), nullable=False),
    sa.Column('event', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('payments',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('order_id', sa.String(length=36), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key'),
    sa.UniqueConstraint('order_id')
    )

def downgrade():
    for table in ["audit_events", "payments", "orders", "purchase_sessions", "products"]:
        op.drop_table(table)
