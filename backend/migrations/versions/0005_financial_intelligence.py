"""Add historical observations and persistent financial decisions."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('price_observations',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('quote_key',sa.String(64),nullable=False,unique=True),
        sa.Column('product_id',sa.String(36),sa.ForeignKey('products.id'),nullable=False),
        sa.Column('merchant_id',sa.String(100),sa.ForeignKey('merchants.id'),nullable=False),
        sa.Column('offer_id',sa.String(160),sa.ForeignKey('product_offers.id'),nullable=False),
        sa.Column('price',sa.Numeric(14,2),nullable=False),sa.Column('currency',sa.String(3),nullable=False),
        sa.Column('observed_at',sa.DateTime(timezone=True),nullable=False),sa.Column('source',sa.String(32),nullable=False),
        sa.Column('verification',sa.String(40),nullable=False),sa.Column('kind',sa.String(32),nullable=False))
    op.create_index('ix_price_observations_product_id','price_observations',['product_id'])
    op.create_table('financial_decisions',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('session_id',sa.String(36),sa.ForeignKey('commerce_sessions.id'),nullable=False),
        sa.Column('parent_id',sa.String(36),sa.ForeignKey('financial_decisions.id')),
        sa.Column('status',sa.String(40),nullable=False),sa.Column('goal',sa.JSON(),nullable=False),
        sa.Column('result',sa.JSON(),nullable=False),sa.Column('workflow',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_financial_decisions_session_id','financial_decisions',['session_id'])
    op.create_table('financial_plan_links',sa.Column('plan_id',sa.String(36),sa.ForeignKey('commerce_plans.id'),primary_key=True),
        sa.Column('decision_id',sa.String(36),sa.ForeignKey('financial_decisions.id'),nullable=False),sa.Column('strategy',sa.String(40),nullable=False))
    op.create_table('scenario_simulations',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('decision_id',sa.String(36),sa.ForeignKey('financial_decisions.id'),nullable=False),
        sa.Column('parameters',sa.JSON(),nullable=False),sa.Column('result',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    for table in ['financial_plan_links','scenario_simulations','financial_decisions','price_observations']:
        if op.get_bind().execute(sa.text(f'SELECT count(*) FROM {table}')).scalar():
            raise RuntimeError('Cannot discard recorded financial evidence or decisions')
    for table in ['financial_plan_links','scenario_simulations','financial_decisions','price_observations']:
        op.drop_table(table)
