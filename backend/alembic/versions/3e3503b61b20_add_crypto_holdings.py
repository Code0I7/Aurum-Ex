"""add crypto holdings, transactions, and sync state

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
        # Cached from the last successful CoinGecko sync — quantity and
        # average buy price are computed from crypto_transactions instead
        # of stored here (see models/crypto.py).
        sa.Column('last_price', sa.Numeric(precision=38, scale=18), nullable=True),
        sa.Column('price_change_1h', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('price_change_24h', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('price_change_7d', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('asset_id'),
    )
    op.create_table(
        'crypto_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column(
            'type',
            sa.Enum('BUY', 'SELL', name='crypto_transaction_type', native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column('quantity', sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column('price_per_unit', sa.Numeric(precision=38, scale=18), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['crypto_holdings.asset_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'crypto_sync_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('crypto_sync_state')
    op.drop_table('crypto_transactions')
    op.drop_table('crypto_holdings')
