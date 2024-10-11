"""Rename reactants' log_titration_rate column to titration_rate

Revision ID: e35ff1ed51d6
Revises: base
Create Date: 2024-10-11 12:26:42.066283
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e35ff1ed51d6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for reactant_type in ['mineral', 'gas', 'element', 'special']:
        op.alter_column(f'{reactant_type}_reactants', 'log_titration_rate', new_column_name='titration_rate')


def downgrade() -> None:
    for reactant_type in ['mineral', 'gas', 'element', 'special']:
        op.alter_column(f'{reactant_type}_reactants', 'titration_rate', new_column_name='log_titration_rate')