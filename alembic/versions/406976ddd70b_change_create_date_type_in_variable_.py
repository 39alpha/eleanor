"""Change create_date type in variable space

Revision ID: 406976ddd70b
Revises: 4cc564b04784
Create Date: 2024-10-12 14:00:54.675439

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '406976ddd70b'
down_revision: Union[str, None] = '4cc564b04784'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('variable_space', 'create_date', type_ = sa.DateTime, postgresql_using="create_date::timestamp without time zone AT TIME ZONE 'US/Arizona'")


def downgrade() -> None:
    op.alter_column('variable_space', 'create_date', type_ = sa.String)
