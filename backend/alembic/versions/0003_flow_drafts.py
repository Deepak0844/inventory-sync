"""flow editor drafts

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("flow_draft_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("suppliers", "flow_draft_json")
