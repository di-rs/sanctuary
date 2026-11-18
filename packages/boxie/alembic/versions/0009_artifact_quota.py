"""Track retained expanded bytes and durable artifact staging reservations."""

import sqlalchemy as sa
from alembic import op

revision = "0009_artifact_quota"
down_revision = "0008_job_output_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("expanded_bytes", sa.BigInteger(), nullable=True))
    op.create_check_constraint(
        "artifact_expanded_bytes", "artifacts", sa.column("expanded_bytes") >= 0
    )
    op.create_index(
        "artifact_retained_usage",
        "artifacts",
        ["consumer_id", "expanded_bytes"],
        postgresql_where=sa.column("collected_at").is_(None),
    )
    op.create_table(
        "artifact_uploads",
        sa.Column("storage_id", sa.Uuid(), primary_key=True),
        sa.Column("consumer_id", sa.String(), nullable=False),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.CheckConstraint(sa.column("reserved_bytes") > 0, name="artifact_upload_reserved_bytes"),
    )


def downgrade() -> None:
    op.drop_table("artifact_uploads")
    op.drop_index("artifact_retained_usage", table_name="artifacts")
    op.drop_constraint("artifact_expanded_bytes", "artifacts", type_="check")
    op.drop_column("artifacts", "expanded_bytes")
