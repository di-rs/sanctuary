"""Persist the Boxie binding and local stop disposition."""

import sqlalchemy as sa
from alembic import op

revision = "0004_stop_reconciliation"
down_revision = "0003_cli_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("session_binding", sa.Column("sandbox_scope", sa.String(), nullable=True))
    op.add_column(
        "session_binding",
        sa.Column("stop_absent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("session_binding", "stop_absent", server_default=None)


def downgrade() -> None:
    op.execute("UPDATE session_binding SET pending_stop = true WHERE stop_absent")
    op.drop_column("session_binding", "stop_absent")
    op.drop_column("session_binding", "sandbox_scope")
