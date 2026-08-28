"""reminder offsets

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('linked_teams', sa.Column('reminder_offsets', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('linked_teams', 'reminder_offsets')
