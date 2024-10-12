"""Add timeout to kernel configuration

Revision ID: 9415b31c7919
Revises: e35ff1ed51d6
Create Date: 2024-10-12 13:02:33.258535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9415b31c7919'
down_revision: Union[str, None] = 'e35ff1ed51d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def column_exists(table_name, column_name):
    bind = op.get_context().bind
    insp = sa.inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)


def upgrade() -> None:
    if not column_exists('kernel', 'timeout'):
        op.add_column('kernel', sa.Column('timeout', sa.Integer, server_default='0'))


def downgrade() -> None:
    if column_exists('kernel', 'timeout'):
        op.drop_column('kernel', 'timeout')
