"""remove suppression id from suppression exceptions primary key

Revision ID: 4b0c583db36a
Revises: 781126d47cbe
Create Date: 2025-04-18 11:58:47.563882

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4b0c583db36a'
down_revision: Union[str, None] = '781126d47cbe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE suppression_exceptions DROP CONSTRAINT suppression_exceptions_pkey')
    op.execute('ALTER TABLE suppression_exceptions ADD PRIMARY KEY (id)')


def downgrade() -> None:
    op.execute('ALTER TABLE suppression_exceptions DROP CONSTRAINT suppression_exceptions_pkey')
    op.execute('ALTER TABLE suppression_exceptions ADD PRIMARY KEY (id, suppression_id)')
