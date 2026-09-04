"""add app_settings

Revision ID: 9f3a2d7c5e11
Revises: 1152a14e9d55
Create Date: 2026-08-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f3a2d7c5e11'
down_revision: Union[str, None] = '1152a14e9d55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Singleton row (id=1) — deliberately NOT seeded here anymore (a prior
    # version of this migration hardcoded `INSERT ... VALUES (1, 'USD')`,
    # which silently ignored AURUM_DEFAULT_CURRENCY on a fresh install: the
    # row already existed by the time app boot's seed_default_app_settings()
    # ran its own get-or-create check, so a non-USD default never took).
    # seed_default_app_settings() runs on every app boot (see main.py's
    # lifespan) and already reads get_settings().default_currency correctly
    # — leaving row creation to it entirely is both simpler and correct for
    # every configured currency, not just USD.


def downgrade() -> None:
    op.drop_table('app_settings')
