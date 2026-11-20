"""Reserve environment zero for the protected branch."""

from alembic import op

revision = "0004_production"
down_revision = "0003_cli_catalog"


def upgrade() -> None:
    op.drop_constraint("positive_pr", "preview", type_="check")
    op.create_check_constraint("environment_number", "preview", "pr >= 0")


def downgrade() -> None:
    op.drop_constraint("environment_number", "preview", type_="check")
    op.create_check_constraint("positive_pr", "preview", "pr > 0")
