"""Phase 12 human-review queue lifecycle fields."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261119_0009"
down_revision: Union[str, None] = "20261119_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "verification_results",
        sa.Column(
            "review_status",
            sa.Enum(
                "pending",
                "in_review",
                "resolved",
                "investigation_requested",
                name="human_review_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
    )
    op.add_column(
        "verification_results",
        sa.Column("assigned_reviewer_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "verification_results",
        sa.Column("review_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_verification_results_assigned_reviewer",
        "verification_results",
        "users",
        ["assigned_reviewer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_verification_results_review_status",
        "verification_results",
        ["review_status"],
    )

    op.drop_constraint(
        "review_action",
        "review_history",
        type_="check",
    )
    op.create_check_constraint(
        "ck_review_history_action_review_action",
        "review_history",
        "review_action IN ('accept_ai', 'reject_ai', 'change_verdict', "
        "'resolve', 'reopen', 'request_investigation')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_review_history_action_review_action",
        "review_history",
        type_="check",
    )
    op.create_check_constraint(
        "review_action",
        "review_history",
        "review_action IN ('accept_ai', 'reject_ai', 'change_verdict', "
        "'resolve', 'reopen')",
    )
    op.drop_index(
        "ix_verification_results_review_status",
        table_name="verification_results",
    )
    op.drop_constraint(
        "fk_verification_results_assigned_reviewer",
        "verification_results",
        type_="foreignkey",
    )
    op.drop_column("verification_results", "review_requested_at")
    op.drop_column("verification_results", "assigned_reviewer_id")
    op.drop_column("verification_results", "review_status")
