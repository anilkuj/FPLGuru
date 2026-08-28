"""live scores

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'player_gw_live',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('gameweek_id', sa.Integer(), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('live_points', sa.Integer(), nullable=False),
        sa.Column('bps', sa.Integer(), nullable=False),
        sa.Column('projected_bonus', sa.Integer(), nullable=False),
        sa.Column('total_points', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['gameweek_id'], ['gameweeks.id'],
                                name=op.f('fk_player_gw_live_gameweek_id_gameweeks')),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'],
                                name=op.f('fk_player_gw_live_player_id_players')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_player_gw_live')),
        sa.UniqueConstraint('player_id', 'gameweek_id',
                            name='uq_player_gw_live_player_id_gameweek_id'),
    )
    op.create_index(op.f('ix_player_gw_live_gameweek_id'), 'player_gw_live',
                    ['gameweek_id'], unique=False)
    op.create_index(op.f('ix_player_gw_live_player_id'), 'player_gw_live',
                    ['player_id'], unique=False)

    op.add_column('fixtures', sa.Column('started', sa.Boolean(), nullable=False,
                                        server_default=sa.text('false')))
    op.add_column('fixtures', sa.Column('finished_provisional', sa.Boolean(), nullable=False,
                                        server_default=sa.text('false')))
    op.add_column('fixtures', sa.Column('minutes', sa.Integer(), nullable=False,
                                        server_default=sa.text('0')))


def downgrade() -> None:
    op.drop_column('fixtures', 'minutes')
    op.drop_column('fixtures', 'finished_provisional')
    op.drop_column('fixtures', 'started')
    op.drop_index(op.f('ix_player_gw_live_player_id'), table_name='player_gw_live')
    op.drop_index(op.f('ix_player_gw_live_gameweek_id'), table_name='player_gw_live')
    op.drop_table('player_gw_live')
