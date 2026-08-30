"""add crypto holdings and sync state

Revision ID: 3e3503b61b20
Revises: f6a4d8b2e017
Create Date: 2026-08-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e3503b61b20'
down_revision: Union[str, None] = 'f6a4d8b2e017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'crypto_holdings',
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('coingecko_id', sa.String(length=100), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('thumb_url', sa.String(length=500), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('asset_id'),
    )
    op.create_table(
        'crypto_sync_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('crypto_sync_state')
    op.drop_table('crypto_holdings')
