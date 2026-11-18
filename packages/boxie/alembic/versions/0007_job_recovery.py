"""Keep job identities independently of the bounded result and lifecycle retention."""

import sqlalchemy as sa
from alembic import op

revision = "0007_job_recovery"
down_revision = "0006_request_correlation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("consumer_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("authorized_boot", sa.Uuid()),
        sa.UniqueConstraint("consumer_id", "idempotency_key"),
        sa.CheckConstraint(
            sa.column("state").in_(
                [
                    "queued",
                    "starting",
                    "running",
                    "succeeded",
                    "failed",
                    "not_started",
                    "outcome_unknown",
                ]
            ),
            name="job_state",
        ),
    )
    op.create_table(
        "job_results",
        sa.Column(
            "sandbox_id",
            sa.Uuid(),
            sa.ForeignKey("sandboxes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("exit_code", sa.Integer(), nullable=False),
        sa.Column("stdout", sa.LargeBinary(), nullable=False),
        sa.Column("stderr", sa.LargeBinary(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("job_results")
    op.drop_table("jobs")
