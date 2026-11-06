"""Immutable authorization digest and execution fencing lease."""
from alembic import op
import sqlalchemy as sa
revision="0004"
down_revision="0003"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("commerce_purchases",sa.Column("authorization_digest",sa.String(64),nullable=True))
    op.add_column("commerce_purchases",sa.Column("execution_token",sa.String(36),nullable=True))
    op.add_column("commerce_purchases",sa.Column("workflow",sa.JSON(),nullable=False,server_default=sa.text("'{}'")))

def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM commerce_purchases")).scalar():
        raise RuntimeError("Cannot discard stored authorization or execution state")
    with op.batch_alter_table("commerce_purchases") as batch:
        batch.drop_column("workflow")
        batch.drop_column("execution_token")
        batch.drop_column("authorization_digest")
