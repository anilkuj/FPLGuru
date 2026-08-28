"""xp rationale

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'xp_rationale',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('gameweek_id', sa.Integer(), nullable=False),
        sa.Column('model_version', sa.String(length=16), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('model', sa.String(length=48), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['gameweek_id'], ['gameweeks.id'],
            name=op.f('fk_xp_rationale_gameweek_id_gameweeks')),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'],
            name=op.f('fk_xp_rationale_player_id_players')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_xp_rationale')),
        sa.UniqueConstraint('player_id', 'gameweek_id', 'model_version',
                            name='uq_xp_rationale_player_id_gameweek_id_model_version'),
    )
    op.create_index(op.f('ix_xp_rationale_gameweek_id'), 'xp_rationale',
                    ['gameweek_id'], unique=False)
    op.create_index(op.f('ix_xp_rationale_player_id'), 'xp_rationale',
                    ['player_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_xp_rationale_player_id'), table_name='xp_rationale')
    op.drop_index(op.f('ix_xp_rationale_gameweek_id'), table_name='xp_rationale')
    op.drop_table('xp_rationale')
