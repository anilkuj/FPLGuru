"""player trends

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('players', sa.Column('transfers_in_event', sa.Integer(), nullable=False,
                                       server_default='0'))
    op.add_column('players', sa.Column('transfers_out_event', sa.Integer(), nullable=False,
                                       server_default='0'))
    op.add_column('players', sa.Column('cost_change_event', sa.Integer(), nullable=False,
                                       server_default='0'))
    op.add_column('players', sa.Column('form', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('players', 'form')
    op.drop_column('players', 'cost_change_event')
    op.drop_column('players', 'transfers_out_event')
    op.drop_column('players', 'transfers_in_event')
