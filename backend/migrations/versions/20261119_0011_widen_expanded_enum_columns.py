"""Widen non-native enum columns for values added by later revisions.

Revision ID: 20261119_0011
Revises: 20261119_0010
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261119_0011"
down_revision: Union[str, None] = "20261119_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMN_LENGTHS = (
    ("claims", "claim_type", 11, 15),
    ("review_history", "action", 13, 21),
    ("reports", "format", 3, 4),
)


def upgrade() -> None:
    for table, column, old_length, new_length in _COLUMN_LENGTHS:
        op.alter_column(
            table,
            column,
            existing_type=sa.String(length=old_length),
            type_=sa.String(length=new_length),
            existing_nullable=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    for table, column, old_length, new_length in reversed(_COLUMN_LENGTHS):
        has_long_values = connection.execute(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM {table} "
                f"WHERE length({column}) > :max_length)"
            ),
            {"max_length": old_length},
        ).scalar_one()
        if has_long_values:
            raise RuntimeError(
                f"Cannot narrow {table}.{column}; existing values exceed "
                f"{old_length} characters."
            )
        op.alter_column(
            table,
            column,
            existing_type=sa.String(length=new_length),
            type_=sa.String(length=old_length),
            existing_nullable=False,
        )
