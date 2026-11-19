"""Phase 11 separate final verdict classification."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261119_0008"
down_revision: Union[str, None] = "20261119_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    verdict_enum = sa.Enum(
        "supported",
        "partly_supported",
        "unsupported",
        "contradictory",
        "possibly_outdated",
        "needs_review",
        name="final_verdict",
        native_enum=False,
        create_constraint=True,
    )
    op.add_column("verification_results", sa.Column("final_verdict", verdict_enum, nullable=True))
    op.add_column("verification_results", sa.Column("classification_method", sa.String(length=80), nullable=True))
    op.add_column("verification_results", sa.Column("classification_reason", sa.Text(), nullable=True))
    op.add_column("verification_results", sa.Column("classification_confidence", sa.Float(), nullable=True))
    op.add_column("verification_results", sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_verification_results_classification_confidence",
        "verification_results",
        "classification_confidence IS NULL OR "
        "(classification_confidence >= 0 AND classification_confidence <= 1)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_verification_results_classification_confidence",
        "verification_results",
        type_="check",
    )
    op.drop_column("verification_results", "classified_at")
    op.drop_column("verification_results", "classification_confidence")
    op.drop_column("verification_results", "classification_reason")
    op.drop_column("verification_results", "classification_method")
    op.drop_column("verification_results", "final_verdict")
