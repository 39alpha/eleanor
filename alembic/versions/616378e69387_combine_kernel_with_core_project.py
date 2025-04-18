"""combine kernel with core project

Revision ID: 616378e69387
Revises: 4b0c583db36a
Create Date: 2025-04-18 12:51:33.476316

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '616378e69387'
down_revision: Union[str, None] = '4b0c583db36a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('orders', 'kernel_version')


def downgrade() -> None:
    op.add_column(
        'orders',
        sa.Column('kernel_version', sa.VARCHAR(), autoincrement=False, nullable=False),
    )
