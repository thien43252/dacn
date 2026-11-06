"""dify runtime: conversation, knowledge base and document ids on the Dify side

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-07 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("dify_conversation_id", sa.String(length=64), nullable=True))
    op.add_column("classes", sa.Column("dify_dataset_id", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_classes_dify_dataset_id", "classes", ["dify_dataset_id"])
    op.add_column("documents", sa.Column("dify_document_id", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("dify_batch", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "dify_batch")
    op.drop_column("documents", "dify_document_id")
    op.drop_constraint("uq_classes_dify_dataset_id", "classes", type_="unique")
    op.drop_column("classes", "dify_dataset_id")
    op.drop_column("conversations", "dify_conversation_id")
