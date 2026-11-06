"""Bind legacy approval to immutable server-side terms; do not infer old approvals."""
from alembic import op
import sqlalchemy as sa
revision='0007'
down_revision='0006'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('orders',sa.Column('purchase_terms',sa.JSON(),nullable=True))
    op.add_column('orders',sa.Column('authorization_digest',sa.String(64),nullable=True))

def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM orders WHERE authorization_digest IS NOT NULL')).scalar():
        raise RuntimeError('Cannot discard approved purchase fingerprints')
    with op.batch_alter_table('orders') as batch:
        batch.drop_column('authorization_digest');batch.drop_column('purchase_terms')
