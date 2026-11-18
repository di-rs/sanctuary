"""Account for pending and retained job output on the owning sandbox."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_job_output_budget"
down_revision = "0007_job_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sandboxes",
        sa.Column(
            "reserved_result_bytes", sa.BigInteger(), nullable=False, server_default=sa.literal(0)
        ),
    )
    sandboxes = sa.table(
        "sandboxes",
        sa.column("id"),
        sa.column("snapshot", JSONB()),
        sa.column("reserved_result_bytes"),
    )
    jobs = sa.table("jobs", sa.column("id"), sa.column("state"))
    results = sa.table(
        "job_results", sa.column("sandbox_id"), sa.column("stdout"), sa.column("stderr")
    )
    op.execute(
        sandboxes.update()
        .where(sandboxes.c.id == jobs.c.id, jobs.c.state.in_(("queued", "starting", "running")))
        .values(reserved_result_bytes=sandboxes.c.snapshot["limits"]["output_bytes"].as_integer())
    )
    op.execute(
        sandboxes.update()
        .where(sandboxes.c.id == results.c.sandbox_id)
        .values(
            reserved_result_bytes=sa.func.octet_length(results.c.stdout)
            + sa.func.octet_length(results.c.stderr)
        )
    )
    op.create_check_constraint(
        "sandbox_result_bytes", "sandboxes", sandboxes.c.reserved_result_bytes >= 0
    )
    op.create_index(
        "sandbox_result_reservations",
        "sandboxes",
        ["consumer_id", "reserved_result_bytes"],
        postgresql_where=sandboxes.c.reserved_result_bytes > 0,
    )


def downgrade() -> None:
    op.drop_index("sandbox_result_reservations", table_name="sandboxes")
    op.drop_constraint("sandbox_result_bytes", "sandboxes", type_="check")
    op.drop_column("sandboxes", "reserved_result_bytes")
