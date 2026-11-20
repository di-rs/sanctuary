"""Schedule orphaned upload retries without changing reservation age or quota."""

import sqlalchemy as sa
from alembic import op

revision = "0010_artifact_orphan_retry"
down_revision = "0009_artifact_quota"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("artifact_uploads", sa.Column("retry_after", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("artifact_uploads", "retry_after")
