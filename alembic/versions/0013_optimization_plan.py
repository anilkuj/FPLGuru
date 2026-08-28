"""optimization plan

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'optimization_plan',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('linked_team_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('horizon', sa.Integer(), nullable=False),
        sa.Column('max_transfers', sa.Integer(), nullable=False),
        sa.Column('model_version', sa.String(length=16), nullable=False),
        sa.Column('payload', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['linked_team_id'], ['linked_teams.id'],
            name=op.f('fk_optimization_plan_linked_team_id_linked_teams')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_optimization_plan')),
    )
    op.create_index(op.f('ix_optimization_plan_created_at'), 'optimization_plan',
                    ['created_at'], unique=False)
    op.create_index(op.f('ix_optimization_plan_linked_team_id'), 'optimization_plan',
                    ['linked_team_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_optimization_plan_linked_team_id'), table_name='optimization_plan')
    op.drop_index(op.f('ix_optimization_plan_created_at'), table_name='optimization_plan')
    op.drop_table('optimization_plan')
