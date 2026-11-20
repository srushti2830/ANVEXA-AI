"""Phase 7 citation detection and mapping fields."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261119_0005"
down_revision: Union[str, None] = "20261119_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("citations", sa.Column("original_marker", sa.Text(), nullable=True))
    op.add_column("citations", sa.Column("normalized_marker", sa.String(length=500), nullable=True))
    op.add_column("citations", sa.Column("journal_or_conference", sa.String(length=1000), nullable=True))
    op.add_column("citations", sa.Column("volume", sa.String(length=50), nullable=True))
    op.add_column("citations", sa.Column("issue", sa.String(length=50), nullable=True))
    op.add_column("citations", sa.Column("page_range", sa.String(length=100), nullable=True))
    op.add_column("citations", sa.Column("paragraph_number", sa.Integer(), nullable=True))
    op.add_column("citations", sa.Column("extraction_method", sa.String(length=120), nullable=True))
    op.create_unique_constraint(
        "uq_citations_version_marker_text",
        "citations",
        ["document_version_id", "normalized_marker", "citation_text"],
    )

    op.add_column(
        "claim_citations",
        sa.Column(
            "mapping_status",
            sa.Enum(
                "matched",
                "unmatched",
                "ambiguous",
                "multiple_matches",
                "missing_reference",
                name="citation_mapping_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default=sa.text("'unmatched'"),
            nullable=False,
        ),
    )
    op.add_column("claim_citations", sa.Column("normalized_marker", sa.String(length=500), nullable=True))
    op.add_column("claim_citations", sa.Column("paragraph_number", sa.Integer(), nullable=True))
    op.create_unique_constraint(
        "uq_claim_citations_claim_citation",
        "claim_citations",
        ["claim_id", "citation_id"],
    )

    op.drop_constraint("citation_style", "citations", type_="check")
    op.create_check_constraint(
        "ck_citations_citation_type_citation_style",
        "citations",
        "citation_type IN ('numeric', 'author_year', 'superscript', 'apa', 'ieee', 'mla', 'vancouver', 'unknown')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_citations_citation_type_citation_style", "citations", type_="check")
    op.create_check_constraint(
        "ck_citations_citation_type_citation_style",
        "citations",
        "citation_type IN ('numeric', 'author_year', 'superscript', 'unknown')",
    )
    op.drop_constraint("uq_claim_citations_claim_citation", "claim_citations", type_="unique")
    op.drop_column("claim_citations", "paragraph_number")
    op.drop_column("claim_citations", "normalized_marker")
    op.drop_column("claim_citations", "mapping_status")
    op.drop_constraint("uq_citations_version_marker_text", "citations", type_="unique")
    op.drop_column("citations", "extraction_method")
    op.drop_column("citations", "paragraph_number")
    op.drop_column("citations", "page_range")
    op.drop_column("citations", "issue")
    op.drop_column("citations", "volume")
    op.drop_column("citations", "journal_or_conference")
    op.drop_column("citations", "normalized_marker")
    op.drop_column("citations", "original_marker")
