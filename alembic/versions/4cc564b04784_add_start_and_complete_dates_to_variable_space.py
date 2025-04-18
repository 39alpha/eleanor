"""Add start and complete dates to variable space

Revision ID: 4cc564b04784
Revises: 6f78dead1916
Create Date: 2024-10-12 13:49:09.224220

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4cc564b04784'
down_revision: Union[str, None] = '6f78dead1916'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    bind = op.get_context().bind
    insp = sa.inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)


def upgrade() -> None:
    if not column_exists('variable_space', 'start_date'):
        op.add_column(
            'variable_space',
            sa.Column('start_date', sa.DateTime, server_default='1970-01-01T12:00:00'),
        )
    if not column_exists('variable_space', 'complete_date'):
        op.add_column(
            'variable_space',
            sa.Column('complete_date', sa.DateTime, server_default='1970-01-01T12:00:00'),
        )


def downgrade() -> None:
    if column_exists('variable_space', 'start_date'):
        op.drop_column('variable_space', 'start_date')
    if column_exists('variable_space', 'complete_date'):
        op.drop_column('variable_space', 'complete_date')
