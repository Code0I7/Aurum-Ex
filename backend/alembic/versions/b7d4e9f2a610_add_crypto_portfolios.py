"""add crypto portfolios

Revision ID: b7d4e9f2a610
Revises: 7b535ef9e189
Create Date: 2026-09-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d4e9f2a610'
down_revision: Union[str, None] = '7b535ef9e189'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'crypto_portfolios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # Every crypto holding needs a portfolio_id (see below) — seed one
    # default portfolio up front so existing holdings have somewhere to
    # land, same "row exists immediately after migrating" reasoning as
    # 9f3a2d7c5e11's app_settings seed.
    op.execute("INSERT INTO crypto_portfolios (id, name, color, is_archived) VALUES (1, 'Main Portfolio', '#2a78d6', false)")
    op.execute("SELECT setval(pg_get_serial_sequence('crypto_portfolios', 'id'), 1)")

    op.add_column('crypto_holdings', sa.Column('portfolio_id', sa.Integer(), nullable=True))
    op.execute("UPDATE crypto_holdings SET portfolio_id = 1")
    op.alter_column('crypto_holdings', 'portfolio_id', nullable=False)
    op.create_foreign_key(
        'fk_crypto_holdings_portfolio_id',
        'crypto_holdings',
        'crypto_portfolios',
        ['portfolio_id'],
        ['id'],
        ondelete='RESTRICT',
    )


def downgrade() -> None:
    op.drop_constraint('fk_crypto_holdings_portfolio_id', 'crypto_holdings', type_='foreignkey')
    op.drop_column('crypto_holdings', 'portfolio_id')
    op.drop_table('crypto_portfolios')
