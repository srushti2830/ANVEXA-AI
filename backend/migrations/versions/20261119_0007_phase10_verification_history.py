"""Phase 10 verification history and structured analysis."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261119_0007"
down_revision: Union[str, None] = "20261119_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "verification_results",
        sa.Column("structured_analysis", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "verification_results",
        sa.Column("supporting_evidence_ids", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "verification_results",
        sa.Column("contradicting_evidence_ids", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "verification_results",
        sa.Column("limitations", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "verification_results",
        sa.Column("unresolved_questions", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "verification_results",
        sa.Column("prompt_version", sa.String(length=80), server_default=sa.text("'phase10-v1'"), nullable=False),
    )
    op.add_column(
        "verification_results",
        sa.Column("requires_human_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("verification_results", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("verification_results", "error_message")
    op.drop_column("verification_results", "requires_human_review")
    op.drop_column("verification_results", "prompt_version")
    op.drop_column("verification_results", "unresolved_questions")
    op.drop_column("verification_results", "limitations")
    op.drop_column("verification_results", "contradicting_evidence_ids")
    op.drop_column("verification_results", "supporting_evidence_ids")
    op.drop_column("verification_results", "structured_analysis")
