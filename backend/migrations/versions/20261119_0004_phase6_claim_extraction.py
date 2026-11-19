"""Phase 6 claim extraction metadata.

Revision ID: 20261119_0004
Revises: 20261119_0003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261119_0004"
down_revision: Union[str, None] = "20261119_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("section_heading", sa.String(length=500), nullable=True))
    op.add_column("claims", sa.Column("extraction_confidence", sa.Float(), nullable=True))
    op.add_column("claims", sa.Column("citation_markers", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    op.add_column("claims", sa.Column("extraction_reason", sa.Text(), nullable=True))

    op.drop_constraint(
        "ck_claims_claim_type_claim_type",
        "claims",
        type_="check",
    )
    op.create_check_constraint(
        "ck_claims_claim_type_claim_type",
        "claims",
        "claim_type IN ('scientific', 'numerical', 'statistical', "
        "'comparative', 'causal', 'methodological', 'medical', 'technical', "
        "'historical', 'general_factual', 'descriptive', 'temporal', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_claims_claim_type_claim_type",
        "claims",
        type_="check",
    )
    op.create_check_constraint(
        "ck_claims_claim_type_claim_type",
        "claims",
        "claim_type IN ('numerical', 'statistical', 'comparative', 'causal', "
        "'descriptive', 'temporal', 'other')",
    )
    op.drop_column("claims", "extraction_reason")
    op.drop_column("claims", "citation_markers")
    op.drop_column("claims", "extraction_confidence")
    op.drop_column("claims", "section_heading")
