"""aurum-ex: начальная схема

Одна миграция вместо семнадцати унаследованных. Схлопнуть их можно ровно
один раз — пока ни одной установки с данными не существует; дальше любое
изменение схемы снова идёт отдельной миграцией, как обычно.

Что здесь появилось сверх оригинальной схемы Aurum:

* banks, participants, counterparties, stores, units, products — справочники,
  на которых держатся группировка счетов по банкам, разрез "на кого
  потрачено", расчёты с людьми и динамика цен на товар;
* currencies и exchange_rates — курсы ЦБ по датам: курс операции
  замораживается в самой транзакции, остатки считаются по текущему;
* transactions — uuid, порядок внутри дня, валюта и курс, участник, магазин,
  контрагент, возвратность расчёта, признак "не учитывать в расчётах";
* transaction_items — позиции чека с количеством, единицей и ценой, все поля
  необязательны;
* accounts — вид и природа разведены, добавлены банк, начальный остаток и
  запрет ухода в минус;
* goals — привязка к счёту и статус: копится, достигнута, отменена;
* credit_terms, plans, work_periods, dashboard_widgets, users, sessions;
* investment_* — единый движок лотов под FIFO, на который позже переедет
  крипта.

Revision ID: 0001_aurum_ex_base
Revises:
Create Date: 2026-09-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_aurum_ex_base"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('app_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('reliable_from', sa.Date(), nullable=True),
    sa.Column('negative_cash_flow_threshold_months', sa.Integer(), nullable=False),
    sa.Column('net_worth_decline_threshold_months', sa.Integer(), nullable=False),
    sa.Column('risky_allocation_threshold_percent', sa.Integer(), nullable=False),
    sa.Column('idle_cash_threshold_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('idle_cash_threshold_days', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('assets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('asset_class', sa.Enum('INVESTMENTS', 'CRYPTO', 'REAL_ESTATE', 'VEHICLES', 'PRECIOUS_METALS', 'OTHER', name='asset_class', native_enum=False, length=20), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('capital_role', sa.Enum('INCOME', 'NEUTRAL', 'DRAIN', name='capital_role', native_enum=False, length=10), nullable=False),
    sa.Column('monthly_cash_flow', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('risk_level', sa.Enum('LOW', 'MEDIUM', 'HIGH', name='risk_level', native_enum=False, length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('banks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.Enum('INCOME', 'EXPENSE', name='category_kind', native_enum=False, length=10), nullable=False),
    sa.Column('icon', sa.String(length=50), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('counterparties',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('crypto_portfolios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('crypto_sync_state',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('currencies',
    sa.Column('code', sa.String(length=3), nullable=False),
    sa.Column('symbol', sa.String(length=8), nullable=True),
    sa.Column('name', sa.String(length=60), nullable=True),
    sa.Column('cbr_nominal', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    op.create_table('dashboard_widgets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('widget_type', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=150), nullable=True),
    sa.Column('period', sa.String(length=30), nullable=False),
    sa.Column('row', sa.Integer(), nullable=False),
    sa.Column('column', sa.Integer(), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_visible', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('exchange_rates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=3), nullable=False),
    sa.Column('rate_date', sa.Date(), nullable=False),
    sa.Column('rate', sa.Numeric(precision=20, scale=10), nullable=False),
    sa.Column('published_for', sa.Date(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', 'rate_date', name='uq_exchange_rate_code_date')
    )
    op.create_index('ix_exchange_rate_date', 'exchange_rates', ['rate_date'], unique=False)
    op.create_table('investment_portfolios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('participants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.Enum('PERSON', 'PET', name='participant_kind', native_enum=False, length=10), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('sessions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('stores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('units',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=20), nullable=False),
    sa.Column('kind', sa.Enum('MASS', 'VOLUME', 'COUNT', 'LENGTH', 'SERVICE', name='unit_kind', native_enum=False, length=10), nullable=False),
    sa.Column('factor', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('is_base', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=100), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('failed_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.Enum('CHECKING', 'SAVINGS', 'CREDIT_CARD', 'CASH', 'INVESTMENT', 'LOAN', 'OTHER', name='account_kind', native_enum=False, length=20), nullable=False),
    sa.Column('nature', sa.Enum('ASSET', 'LIABILITY', name='account_nature', native_enum=False, length=10), nullable=False),
    sa.Column('bank_id', sa.Integer(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('opening_balance', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('opening_date', sa.Date(), nullable=True),
    sa.Column('allow_negative', sa.Boolean(), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['bank_id'], ['banks.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('asset_valuations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('asset_id', sa.Integer(), nullable=False),
    sa.Column('value', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('as_of_date', sa.Date(), nullable=False),
    sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('asset_id', 'as_of_date', name='uq_asset_valuation_date')
    )
    op.create_table('budgets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('monthly_limit', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('category_id')
    )
    op.create_table('crypto_holdings',
    sa.Column('asset_id', sa.Integer(), nullable=False),
    sa.Column('portfolio_id', sa.Integer(), nullable=False),
    sa.Column('coingecko_id', sa.String(length=100), nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('thumb_url', sa.String(length=500), nullable=True),
    sa.Column('last_price', sa.Numeric(precision=38, scale=18), nullable=True),
    sa.Column('price_change_1h', sa.Numeric(precision=10, scale=4), nullable=True),
    sa.Column('price_change_24h', sa.Numeric(precision=10, scale=4), nullable=True),
    sa.Column('price_change_7d', sa.Numeric(precision=10, scale=4), nullable=True),
    sa.Column('price_change_30d', sa.Numeric(precision=10, scale=4), nullable=True),
    sa.Column('price_change_1y', sa.Numeric(precision=10, scale=4), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['portfolio_id'], ['crypto_portfolios.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('asset_id')
    )
    op.create_table('investment_holdings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('portfolio_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('ticker', sa.String(length=30), nullable=True),
    sa.Column('kind', sa.Enum('STOCK', 'BOND', 'FUND', 'CRYPTO', 'METAL', 'OTHER', name='investment_kind', native_enum=False, length=10), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('external_id', sa.String(length=100), nullable=True),
    sa.Column('last_price', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('last_price_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('risk_level', sa.Enum('LOW', 'MEDIUM', 'HIGH', name='investment_risk_level', native_enum=False, length=10), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['portfolio_id'], ['investment_portfolios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('plans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('participant_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.Enum('ONE_OFF', 'MONTHLY', 'DAILY', name='plan_kind', native_enum=False, length=10), nullable=False),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('workdays_only', sa.Boolean(), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('products',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('unit_id', sa.Integer(), nullable=True),
    sa.Column('barcode', sa.String(length=64), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['unit_id'], ['units.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_products_barcode'), 'products', ['barcode'], unique=False)
    op.create_table('work_periods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('participant_id', sa.Integer(), nullable=True),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('month', sa.Integer(), nullable=False),
    sa.Column('hours', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('workdays', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('participant_id', 'year', 'month', name='uq_work_period_participant_month')
    )
    op.create_table('credit_terms',
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('annual_rate_percent', sa.Numeric(precision=6, scale=3), nullable=True),
    sa.Column('credit_limit', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('grace_days', sa.Integer(), nullable=True),
    sa.Column('payment_day', sa.Integer(), nullable=True),
    sa.Column('minimum_payment', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('opened_on', sa.Date(), nullable=True),
    sa.Column('closes_on', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('account_id')
    )
    op.create_table('crypto_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('asset_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('BUY', 'SELL', name='crypto_transaction_type', native_enum=False, length=10), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=38, scale=18), nullable=False),
    sa.Column('price_per_unit', sa.Numeric(precision=38, scale=18), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['asset_id'], ['crypto_holdings.asset_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('goals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('target_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('target_date', sa.Date(), nullable=True),
    sa.Column('account_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('ACTIVE', 'ACHIEVED', 'CANCELLED', name='goal_status', native_enum=False, length=10), nullable=False),
    sa.Column('closed_at', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('investment_trades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('holding_id', sa.Integer(), nullable=False),
    sa.Column('side', sa.Enum('BUY', 'SELL', name='trade_side', native_enum=False, length=10), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=28, scale=8), nullable=False),
    sa.Column('price_per_unit', sa.Numeric(precision=24, scale=8), nullable=False),
    sa.Column('fee', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('trade_date', sa.Date(), nullable=False),
    sa.Column('day_order', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['holding_id'], ['investment_holdings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('recurring_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('transfer_account_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.Enum('INCOME', 'EXPENSE', 'TRANSFER', 'EXTERNAL_IN', 'EXTERNAL_OUT', name='recurring_transaction_type', native_enum=False, length=15), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('merchant', sa.String(length=150), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('frequency', sa.Enum('WEEKLY', 'MONTHLY', 'YEARLY', name='recurring_frequency', native_enum=False, length=10), nullable=False),
    sa.Column('anchor_date', sa.Date(), nullable=False),
    sa.Column('last_posted_date', sa.Date(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['transfer_account_id'], ['accounts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uuid', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('transfer_account_id', sa.Integer(), nullable=True),
    sa.Column('participant_id', sa.Integer(), nullable=True),
    sa.Column('store_id', sa.Integer(), nullable=True),
    sa.Column('counterparty_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.Enum('INCOME', 'EXPENSE', 'TRANSFER', 'EXTERNAL_IN', 'EXTERNAL_OUT', name='transaction_type', native_enum=False, length=15), nullable=False),
    sa.Column('settlement_kind', sa.Enum('GIFT', 'LOAN_OUT', 'LOAN_IN', 'REPAYMENT', name='settlement_kind', native_enum=False, length=15), nullable=True),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=20, scale=10), nullable=False),
    sa.Column('amount_base', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('merchant', sa.String(length=150), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('day_order', sa.Integer(), nullable=False),
    sa.Column('is_excluded', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['counterparty_id'], ['counterparties.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['transfer_account_id'], ['accounts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_transactions_uuid'), 'transactions', ['uuid'], unique=True)
    op.create_table('goal_contributions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('goal_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.Column('transaction_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['goal_id'], ['goals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('transaction_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('unit_id', sa.Integer(), nullable=True),
    sa.Column('price', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['unit_id'], ['units.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('transaction_splits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('transaction_tags',
    sa.Column('transaction_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('transaction_id', 'tag_id')
    )


def downgrade() -> None:
    op.drop_table('transaction_tags')
    op.drop_table('transaction_splits')
    op.drop_table('transaction_items')
    op.drop_table('goal_contributions')
    op.drop_table('transactions')
    op.drop_table('recurring_transactions')
    op.drop_table('investment_trades')
    op.drop_table('goals')
    op.drop_table('crypto_transactions')
    op.drop_table('credit_terms')
    op.drop_table('work_periods')
    op.drop_table('products')
    op.drop_table('plans')
    op.drop_table('investment_holdings')
    op.drop_table('crypto_holdings')
    op.drop_table('budgets')
    op.drop_table('asset_valuations')
    op.drop_table('accounts')
    op.drop_table('users')
    op.drop_table('units')
    op.drop_table('tags')
    op.drop_table('stores')
    op.drop_table('sessions')
    op.drop_table('participants')
    op.drop_table('investment_portfolios')
    op.drop_table('exchange_rates')
    op.drop_table('dashboard_widgets')
    op.drop_table('currencies')
    op.drop_table('crypto_sync_state')
    op.drop_table('crypto_portfolios')
    op.drop_table('counterparties')
    op.drop_table('categories')
    op.drop_table('banks')
    op.drop_table('assets')
    op.drop_table('app_settings')
