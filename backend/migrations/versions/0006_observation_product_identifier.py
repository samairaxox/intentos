"""Match historical product references to the existing 64-character catalog IDs."""
from alembic import op
import sqlalchemy as sa
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('price_observations') as batch:
        batch.alter_column('product_id',existing_type=sa.String(36),type_=sa.String(64),existing_nullable=False)


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM price_observations WHERE length(product_id)>36')).scalar():
        raise RuntimeError('Cannot truncate historical product identifiers')
    with op.batch_alter_table('price_observations') as batch:
        batch.alter_column('product_id',existing_type=sa.String(64),type_=sa.String(36),existing_nullable=False)
