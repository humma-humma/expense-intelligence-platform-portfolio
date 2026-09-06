"""Add OCR line items and evidence.

Revision ID: 20260902_0002
Revises: 20260830_0001
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0002"
down_revision: str | None = "20260830_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("receipt_jobs", sa.Column("ocr_result_key", sa.String(512), nullable=True))
    op.add_column("receipts", sa.Column("confidence", sa.Numeric(5, 2), nullable=True))
    op.add_column("receipts", sa.Column("provider", sa.String(100), nullable=True))
    op.add_column("receipts", sa.Column("provider_version", sa.String(100), nullable=True))
    op.add_column("receipts", sa.Column("validation_warnings", sa.JSON(), nullable=True))
    op.execute(
        "UPDATE receipts SET confidence = 100, provider = 'fake', validation_warnings = '[]'::json"
    )
    op.alter_column("receipts", "confidence", nullable=False)
    op.alter_column("receipts", "provider", nullable=False)
    op.alter_column("receipts", "validation_warnings", nullable=False)

    op.create_table(
        "receipt_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=True),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ocr_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_item_id", sa.Uuid(), nullable=True),
        sa.Column("field_type", sa.String(100), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("bounding_box", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["receipt_item_id"], ["receipt_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ocr_observations")
    op.drop_table("receipt_items")
    op.drop_column("receipts", "validation_warnings")
    op.drop_column("receipts", "provider_version")
    op.drop_column("receipts", "provider")
    op.drop_column("receipts", "confidence")
    op.drop_column("receipt_jobs", "ocr_result_key")
