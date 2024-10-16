"""Add exit_code to huffer result

Revision ID: 1ba7026c4000
Revises: 406976ddd70b
Create Date: 2024-10-16 12:06:54.780461

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ba7026c4000'
down_revision: Union[str, None] = '406976ddd70b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    bind = op.get_context().bind
    insp = sa.inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)


def upgrade() -> None:
    if not column_exists('huffer', 'exit_code'):
        op.add_column('huffer', sa.Column('exit_code', sa.Integer, server_default='0'))


def downgrade() -> None:
    if column_exists('huffer', 'exit_code'):
        op.drop_column('huffer', 'exit_code')
