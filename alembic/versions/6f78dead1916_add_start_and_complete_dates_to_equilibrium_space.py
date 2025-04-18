"""Add start and complete dates to equilibrium space

Revision ID: 6f78dead1916
Revises: 9415b31c7919
Create Date: 2024-10-12 13:24:26.708146

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6f78dead1916'
down_revision: Union[str, None] = '9415b31c7919'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    bind = op.get_context().bind
    insp = sa.inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)


def upgrade() -> None:
    if not column_exists('equilibrium_space', 'start_date'):
        op.add_column(
            'equilibrium_space',
            sa.Column('start_date', sa.DateTime, server_default='1970-01-01T12:00:00'),
        )
    if not column_exists('equilibrium_space', 'complete_date'):
        op.add_column(
            'equilibrium_space',
            sa.Column('complete_date', sa.DateTime, server_default='1970-01-01T12:00:00'),
        )


def downgrade() -> None:
    if column_exists('equilibrium_space', 'start_date'):
        op.drop_column('equilibrium_space', 'start_date')
    if column_exists('equilibrium_space', 'complete_date'):
        op.drop_column('equilibrium_space', 'complete_date')
