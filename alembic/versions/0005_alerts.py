"""alerts

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'alerts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('linked_team_id', sa.BigInteger(), nullable=False),
        sa.Column('gameweek_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=24), nullable=False),
        sa.Column('dedup_key', sa.String(length=128), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('body', sa.String(), server_default='', nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('suppressed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['gameweek_id'], ['gameweeks.id'],
                                name=op.f('fk_alerts_gameweek_id_gameweeks')),
        sa.ForeignKeyConstraint(['linked_team_id'], ['linked_teams.id'],
                                name=op.f('fk_alerts_linked_team_id_linked_teams')),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'],
                                name=op.f('fk_alerts_player_id_players')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts')),
        sa.UniqueConstraint('linked_team_id', 'dedup_key',
                            name='uq_alerts_linked_team_id_dedup_key'),
    )
    op.create_index(op.f('ix_alerts_gameweek_id'), 'alerts', ['gameweek_id'], unique=False)
    op.create_index(op.f('ix_alerts_linked_team_id'), 'alerts', ['linked_team_id'], unique=False)
    op.add_column('linked_teams', sa.Column('alert_cap', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('linked_teams', 'alert_cap')
    op.drop_index(op.f('ix_alerts_linked_team_id'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_gameweek_id'), table_name='alerts')
    op.drop_table('alerts')
