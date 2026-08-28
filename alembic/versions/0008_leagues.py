"""leagues

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'linked_team_leagues',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('linked_team_id', sa.BigInteger(), nullable=False),
        sa.Column('league_id', sa.Integer(), nullable=False),
        sa.Column('league_name', sa.String(length=128), nullable=False),
        sa.Column('entry_rank', sa.Integer(), nullable=True),
        sa.Column('entry_last_rank', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['linked_team_id'], ['linked_teams.id'],
            name=op.f('fk_linked_team_leagues_linked_team_id_linked_teams')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_linked_team_leagues')),
        sa.UniqueConstraint('linked_team_id', 'league_id',
            name='uq_linked_team_leagues_linked_team_id_league_id'),
    )
    op.create_index(op.f('ix_linked_team_leagues_league_id'), 'linked_team_leagues',
                    ['league_id'], unique=False)
    op.create_index(op.f('ix_linked_team_leagues_linked_team_id'), 'linked_team_leagues',
                    ['linked_team_id'], unique=False)
    op.create_table(
        'league_standings',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('league_id', sa.Integer(), nullable=False),
        sa.Column('entry_id', sa.Integer(), nullable=False),
        sa.Column('entry_name', sa.String(length=128), nullable=False),
        sa.Column('player_name', sa.String(length=128), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('last_rank', sa.Integer(), nullable=True),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('event_total', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_league_standings')),
        sa.UniqueConstraint('league_id', 'entry_id',
            name='uq_league_standings_league_id_entry_id'),
    )
    op.create_index(op.f('ix_league_standings_entry_id'), 'league_standings',
                    ['entry_id'], unique=False)
    op.create_index(op.f('ix_league_standings_league_id'), 'league_standings',
                    ['league_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_league_standings_league_id'), table_name='league_standings')
    op.drop_index(op.f('ix_league_standings_entry_id'), table_name='league_standings')
    op.drop_table('league_standings')
    op.drop_index(op.f('ix_linked_team_leagues_linked_team_id'), table_name='linked_team_leagues')
    op.drop_index(op.f('ix_linked_team_leagues_league_id'), table_name='linked_team_leagues')
    op.drop_table('linked_team_leagues')
