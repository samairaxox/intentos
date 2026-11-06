from alembic import op
import sqlalchemy as sa
revision="0003"
down_revision="0002"
branch_labels=None
depends_on=None

def upgrade():
    """Frozen additive Phase 3 schema."""
    op.create_table('merchants',
    sa.Column('id', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('available', sa.Boolean(), nullable=False),
    sa.Column('source_type', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mock_provider_receipts',
    sa.Column('idempotency_key', sa.String(length=160), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('outcome', sa.String(length=40), nullable=False),
    sa.Column('reference', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('idempotency_key')
    )
    op.create_table('commerce_sessions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('intent', sa.JSON(), nullable=False),
    sa.Column('conversation', sa.JSON(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('latest_plan_id', sa.String(length=36), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['purchase_sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('product_offers',
    sa.Column('id', sa.String(length=160), nullable=False),
    sa.Column('product_id', sa.String(length=64), nullable=False),
    sa.Column('merchant_id', sa.String(length=100), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('commerce_plans',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('parent_id', sa.String(length=36), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('intent', sa.JSON(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=False),
    sa.Column('workflow', sa.JSON(), nullable=False),
    sa.Column('changes', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['commerce_plans.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['commerce_sessions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id', 'version', name='uq_commerce_plan_version')
    )
    op.create_table('workflow_traces',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('workflow_id', sa.String(length=36), nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('node', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['commerce_sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workflow_traces_workflow_id'), 'workflow_traces', ['workflow_id'], unique=False)
    op.create_table('commerce_purchases',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('plan_id', sa.String(length=36), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('alternative_index', sa.Integer(), nullable=False),
    sa.Column('execution_key', sa.String(length=100), nullable=True),
    sa.Column('execution_modes', sa.JSON(), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['plan_id'], ['commerce_plans.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('execution_key'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_table('offer_snapshots',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('plan_id', sa.String(length=36), nullable=False),
    sa.Column('offer_id', sa.String(length=160), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['offer_id'], ['product_offers.id'], ),
    sa.ForeignKeyConstraint(['plan_id'], ['commerce_plans.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('merchant_suborders',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('purchase_id', sa.String(length=36), nullable=False),
    sa.Column('merchant_id', sa.String(length=100), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('items', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id'], ),
    sa.ForeignKeyConstraint(['purchase_id'], ['commerce_purchases.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('purchase_id', 'merchant_id', name='uq_purchase_merchant')
    )
    op.create_table('payment_intents',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('suborder_id', sa.String(length=36), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.ForeignKeyConstraint(['suborder_id'], ['merchant_suborders.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('suborder_id')
    )
    op.create_table('payment_attempts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('intent_id', sa.String(length=36), nullable=False),
    sa.Column('idempotency_key', sa.String(length=160), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('simulation', sa.String(length=40), nullable=False),
    sa.Column('attempt_number', sa.Integer(), nullable=False),
    sa.Column('retry_after', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['intent_id'], ['payment_intents.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key'),
    sa.UniqueConstraint('intent_id', 'attempt_number', name='uq_intent_attempt_number')
    )
    op.create_table('payment_reconciliations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('attempt_id', sa.String(length=36), nullable=False),
    sa.Column('outcome', sa.String(length=40), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['attempt_id'], ['payment_attempts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###

def downgrade():
    connection=op.get_bind()
    if connection.execute(sa.text("SELECT count(*) FROM commerce_purchases")).scalar():
        raise RuntimeError("Cannot discard commerce payment history; archive through an explicit migration")
    op.drop_table('payment_reconciliations')
    op.drop_table('payment_attempts')
    op.drop_table('payment_intents')
    op.drop_table('merchant_suborders')
    op.drop_table('offer_snapshots')
    op.drop_table('commerce_purchases')
    op.drop_table('workflow_traces')
    op.drop_table('commerce_plans')
    op.drop_table('product_offers')
    op.drop_table('commerce_sessions')
    op.drop_table('mock_provider_receipts')
    op.drop_table('merchants')
