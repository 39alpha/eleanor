"""autoincrement suppression ids

Revision ID: 781126d47cbe
Revises: 1ba7026c4000
Create Date: 2025-01-27 20:19:12.279831

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '781126d47cbe'
down_revision: Union[str, None] = '1ba7026c4000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    bind = op.get_context().bind
    insp = sa.inspect(bind)
    columns = insp.get_columns(table_name)
    return any(c["name"] == column_name for c in columns)


def upgrade() -> None:
    if column_exists('suppression_exceptions', 'id'):
        op.execute('CREATE SEQUENCE suppression_exceptions_id_seq OWNED BY suppression_exceptions.id')
        op.execute(
            "ALTER TABLE suppression_exceptions ALTER COLUMN id SET DEFAULT nextval('suppression_exceptions_id_seq')")
        op.execute(
            sa.text(
                "SELECT setval(pg_get_serial_sequence('suppression_exceptions', 'id'), max(id)) FROM suppression_exceptions"
            ))
    if column_exists('suppression_exceptions', 'suppression_id'):
        op.alter_column('suppression_exceptions', 'suppression_id', nullable=False)


def downgrade() -> None:
    if column_exists('suppression_exceptions', 'id'):
        op.execute(sa.text('ALTER TABLE suppression_exceptions ALTER COLUMN id DROP DEFAULT'))
        op.execute(sa.text('DROP SEQUENCE suppression_exceptions_id_seq'))
