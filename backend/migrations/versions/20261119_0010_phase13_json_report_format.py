"""Phase 13 JSON report format."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261119_0010"
down_revision: Union[str, None] = "20261119_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "report_format",
        "reports",
        type_="check",
    )
    op.create_check_constraint(
        "ck_reports_format_report_format",
        "reports",
        "format IN ('pdf', 'csv', 'json')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_reports_format_report_format",
        "reports",
        type_="check",
    )
    op.create_check_constraint(
        "report_format",
        "reports",
        "format IN ('pdf', 'csv')",
    )
