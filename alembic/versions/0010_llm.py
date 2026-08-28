"""llm

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_calls',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('feature', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=48), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False),
        sa.Column('completion_tokens', sa.Integer(), nullable=False),
        sa.Column('est_cost_usd', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_calls')),
    )
    op.create_index(op.f('ix_llm_calls_created_at'), 'llm_calls', ['created_at'], unique=False)
    op.create_index(op.f('ix_llm_calls_feature'), 'llm_calls', ['feature'], unique=False)
    op.create_table(
        'captain_rationale',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('gameweek_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('model', sa.String(length=48), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['gameweek_id'], ['gameweeks.id'],
            name=op.f('fk_captain_rationale_gameweek_id_gameweeks')),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'],
            name=op.f('fk_captain_rationale_player_id_players')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_captain_rationale')),
        sa.UniqueConstraint('player_id', 'gameweek_id', 'kind',
            name='uq_captain_rationale_player_id_gameweek_id_kind'),
    )
    op.create_index(op.f('ix_captain_rationale_gameweek_id'), 'captain_rationale',
                    ['gameweek_id'], unique=False)
    op.create_index(op.f('ix_captain_rationale_player_id'), 'captain_rationale',
                    ['player_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_captain_rationale_player_id'), table_name='captain_rationale')
    op.drop_index(op.f('ix_captain_rationale_gameweek_id'), table_name='captain_rationale')
    op.drop_table('captain_rationale')
    op.drop_index(op.f('ix_llm_calls_feature'), table_name='llm_calls')
    op.drop_index(op.f('ix_llm_calls_created_at'), table_name='llm_calls')
    op.drop_table('llm_calls')
