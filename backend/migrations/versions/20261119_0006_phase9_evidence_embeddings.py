"""Phase 9 evidence passage and claim embedding metadata."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261119_0006"
down_revision: Union[str, None] = "20261119_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evidence_passages", sa.Column("claim_id", sa.Uuid(), nullable=True))
    op.add_column("evidence_passages", sa.Column("paragraph_number", sa.Integer(), nullable=True))
    op.add_column(
        "evidence_passages",
        sa.Column(
            "content_type",
            sa.Enum(
                "abstract",
                "full_text",
                name="evidence_content_type",
                native_enum=False,
                create_constraint=True,
            ),
            server_default=sa.text("'full_text'"),
            nullable=False,
        ),
    )
    op.add_column("evidence_passages", sa.Column("extraction_method", sa.String(length=120), nullable=True))
    op.add_column("evidence_passages", sa.Column("source_url", sa.String(length=2048), nullable=True))
    op.add_column("evidence_passages", sa.Column("doi", sa.String(length=255), nullable=True))
    op.add_column("evidence_passages", sa.Column("passage_hash", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_evidence_passages_claim",
        "evidence_passages",
        "claims",
        ["claim_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_evidence_passages_claim_location",
        "evidence_passages",
        ["source_version_id", "passage_index", "claim_id"],
    )

    op.alter_column(
        "embeddings",
        "evidence_passage_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.add_column("embeddings", sa.Column("claim_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_embeddings_claim",
        "embeddings",
        ["claim_id"],
    )
    op.create_foreign_key(
        "fk_embeddings_claim",
        "embeddings",
        "claims",
        ["claim_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_embeddings_owner",
        "embeddings",
        "(evidence_passage_id IS NOT NULL) OR (claim_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_embeddings_owner", "embeddings", type_="check")
    op.drop_constraint("fk_embeddings_claim", "embeddings", type_="foreignkey")
    op.drop_constraint("uq_embeddings_claim", "embeddings", type_="unique")
    op.drop_column("embeddings", "claim_id")
    op.alter_column(
        "embeddings",
        "evidence_passage_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_constraint("uq_evidence_passages_claim_location", "evidence_passages", type_="unique")
    op.drop_constraint("fk_evidence_passages_claim", "evidence_passages", type_="foreignkey")
    op.drop_column("evidence_passages", "passage_hash")
    op.drop_column("evidence_passages", "doi")
    op.drop_column("evidence_passages", "source_url")
    op.drop_column("evidence_passages", "extraction_method")
    op.drop_column("evidence_passages", "content_type")
    op.drop_column("evidence_passages", "paragraph_number")
    op.drop_column("evidence_passages", "claim_id")
