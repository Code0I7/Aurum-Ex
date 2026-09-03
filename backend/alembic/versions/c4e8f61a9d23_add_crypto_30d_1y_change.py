"""add crypto price_change_30d/1y

Revision ID: c4e8f61a9d23
Revises: b7d4e9f2a610
Create Date: 2026-09-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8f61a9d23'
down_revision: Union[str, None] = 'b7d4e9f2a610'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crypto_holdings', sa.Column('price_change_30d', sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column('crypto_holdings', sa.Column('price_change_1y', sa.Numeric(precision=10, scale=4), nullable=True))


def downgrade() -> None:
    op.drop_column('crypto_holdings', 'price_change_1y')
    op.drop_column('crypto_holdings', 'price_change_30d')
