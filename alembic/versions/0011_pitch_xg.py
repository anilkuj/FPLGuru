"""pitch xg

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pitch_team_map',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pitch_team_id', sa.String(length=24), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('pitch_name', sa.String(length=64), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'],
            name=op.f('fk_pitch_team_map_team_id_teams')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pitch_team_map')),
        sa.UniqueConstraint('pitch_team_id', name='uq_pitch_team_map_pitch_team_id'),
    )
    op.create_index(op.f('ix_pitch_team_map_team_id'), 'pitch_team_map', ['team_id'], unique=False)
    op.create_table(
        'pitch_player_map',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pitch_player_id', sa.String(length=24), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('pitch_name', sa.String(length=64), nullable=False),
        sa.Column('method', sa.String(length=12), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'],
            name=op.f('fk_pitch_player_map_player_id_players')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pitch_player_map')),
        sa.UniqueConstraint('pitch_player_id', name='uq_pitch_player_map_pitch_player_id'),
    )
    op.create_index(op.f('ix_pitch_player_map_player_id'), 'pitch_player_map',
                    ['player_id'], unique=False)
    op.create_table(
        'player_xg',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('fixture_id', sa.Integer(), nullable=False),
        sa.Column('gameweek_id', sa.Integer(), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('xg', sa.Float(), nullable=False),
        sa.Column('xg_ot', sa.Float(), nullable=False),
        sa.Column('xag', sa.Float(), nullable=False),
        sa.Column('key_passes', sa.Integer(), nullable=False),
        sa.Column('chances_created', sa.Integer(), nullable=False),
        sa.Column('vaep', sa.Float(), nullable=False),
        sa.Column('pitch_match_id', sa.String(length=24), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['fixture_id'], ['fixtures.id'],
            name=op.f('fk_player_xg_fixture_id_fixtures')),
        sa.ForeignKeyConstraint(['gameweek_id'], ['gameweeks.id'],
            name=op.f('fk_player_xg_gameweek_id_gameweeks')),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'],
            name=op.f('fk_player_xg_player_id_players')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_player_xg')),
        sa.UniqueConstraint('player_id', 'fixture_id', name='uq_player_xg_player_id_fixture_id'),
    )
    op.create_index(op.f('ix_player_xg_fixture_id'), 'player_xg', ['fixture_id'], unique=False)
    op.create_index(op.f('ix_player_xg_gameweek_id'), 'player_xg', ['gameweek_id'], unique=False)
    op.create_index(op.f('ix_player_xg_player_id'), 'player_xg', ['player_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_player_xg_player_id'), table_name='player_xg')
    op.drop_index(op.f('ix_player_xg_gameweek_id'), table_name='player_xg')
    op.drop_index(op.f('ix_player_xg_fixture_id'), table_name='player_xg')
    op.drop_table('player_xg')
    op.drop_index(op.f('ix_pitch_player_map_player_id'), table_name='pitch_player_map')
    op.drop_table('pitch_player_map')
    op.drop_index(op.f('ix_pitch_team_map_team_id'), table_name='pitch_team_map')
    op.drop_table('pitch_team_map')
