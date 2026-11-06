"""Ownership is server-provisioned; existing unowned records remain unclaimed."""
from alembic import op
import sqlalchemy as sa
revision='0008'
down_revision='0007'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('purchase_sessions',sa.Column('owner_id',sa.String(160),nullable=True))

def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM purchase_sessions WHERE owner_id IS NOT NULL')).scalar():
        raise RuntimeError('Cannot discard purchase ownership')
    with op.batch_alter_table('purchase_sessions') as batch:batch.drop_column('owner_id')
