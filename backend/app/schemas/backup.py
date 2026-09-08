"""Shape of a full-database backup file (see services/backup_service.py)."""
from datetime import date as date_
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    AccountKind,
    AccountNature,
    AssetClass,
    CapitalRole,
    CategoryKind,
    CryptoTransactionType,
    GoalStatus,
    InvestmentKind,
    ParticipantKind,
    PlanKind,
    RecurringFrequency,
    RiskLevel,
    SettlementKind,
    TradeSide,
    TransactionType,
    UnitKind,
)


class AccountBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    # Переименовано вместе с моделью: type -> kind (см. models/enums.py).
    kind: AccountKind
    currency: str
    color: str | None
    is_archived: bool

    # Поля Aurum-Ex со значениями по умолчанию — бэкап, снятый до их
    # появления, восстанавливается без правки файла.
    nature: AccountNature = AccountNature.ASSET
    bank_id: int | None = None
    opening_balance: Decimal = Decimal("0")
    opening_date: date_ | None = None
    allow_negative: bool = False


class CategoryBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: CategoryKind
    icon: str | None
    color: str
    sort_order: int
    is_default: bool
    # Defaulted so a backup exported before subcategories existed still
    # imports cleanly under the same format version.
    parent_id: int | None = None
    # То же и здесь: копия, снятая до появления списка наблюдения,
    # восстанавливается с пустым списком, а не падает.
    is_watched: bool = False


class TagBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TransactionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Публичный идентификатор записи. Переносится, чтобы ссылка на операцию,
    # выписанная вне приложения, пережила восстановление; новый в этом
    # случае означал бы, что все прежние ссылки указывают в никуда.
    uuid: UUID | None = None
    account_id: int
    category_id: int | None
    transfer_account_id: int | None
    type: TransactionType
    amount: Decimal
    description: str | None = None
    merchant: str | None
    date: date_

    # Поля Aurum-Ex. У всех есть значение по умолчанию, поэтому бэкап,
    # снятый до их появления, восстанавливается без правки файла: валюта
    # берётся базовой, курс — единичным, сумма в базовой валюте равна
    # исходной. Ровно тот случай, ради которого в файл пишется версия
    # приложения (см. APP_VERSION в core/config.py).
    currency: str = "RUB"
    exchange_rate: Decimal = Decimal("1")
    amount_base: Decimal | None = None
    participant_id: int | None = None
    store_id: int | None = None
    counterparty_id: int | None = None
    settlement_kind: SettlementKind | None = None
    is_excluded: bool = False
    day_order: int = 0

    @model_validator(mode="after")
    def _fill_amount_base(self) -> "TransactionBackup":
        # Старый бэкап не знает о сумме в базовой валюте — для однвалютной
        # установки она совпадает с самой суммой.
        if self.amount_base is None:
            self.amount_base = self.amount
        return self

    # Defaulted so a backup exported before tags existed still imports
    # cleanly under the same format version. Not a plain column — populated
    # explicitly in build_backup() from the `tags` relationship, since
    # from_attributes can't map a `tags` relationship to a `tag_ids` field.
    tag_ids: list[int] = Field(default_factory=list)


class TransactionSplitBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: int
    category_id: int | None
    amount: Decimal
    note: str | None


class AssetBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    asset_class: AssetClass
    currency: str
    notes: str | None
    # Defaulted so a backup exported before capital_role/monthly_cash_flow
    # existed still imports cleanly under the same format version.
    capital_role: CapitalRole = CapitalRole.NEUTRAL
    monthly_cash_flow: Decimal | None = None
    # Defaulted so a backup exported before risk_level existed still
    # imports cleanly under the same format version.
    risk_level: RiskLevel = RiskLevel.MEDIUM
    # Квартира, в которой живут, и машина, на которой ездят. По умолчанию
    # не входят в главную цифру капитала: шесть миллионов, из которых 5,8
    # — жильё, которое не продадут, — число, на которое нельзя опереться.
    is_personal_use: bool = False

class AssetValuationBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    value: Decimal
    as_of_date: date_


class CryptoPortfolioBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None
    is_archived: bool


class CryptoHoldingBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # asset_id doubles as this row's own primary key (see
    # models/crypto.py's CryptoHolding) — there's no separate `id`. No
    # quantity here — it's derived from crypto_transactions below, not
    # stored.
    asset_id: int
    # Defaulted so a backup exported before crypto portfolios existed still
    # imports cleanly under the same format version — restore_backup()
    # resolves a missing/unknown portfolio_id to an auto-created fallback
    # portfolio (see services/backup_service.py).
    portfolio_id: int | None = None
    coingecko_id: str
    symbol: str
    name: str
    thumb_url: str | None
    last_price: Decimal | None = None
    price_change_1h: Decimal | None = None
    price_change_24h: Decimal | None = None
    price_change_7d: Decimal | None = None
    # Defaulted so a backup exported before 30d/1y existed still imports
    # cleanly under the same format version.
    price_change_30d: Decimal | None = None
    price_change_1y: Decimal | None = None


class CryptoTransactionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    type: CryptoTransactionType
    quantity: Decimal
    price_per_unit: Decimal
    date: date_
    note: str | None


class BudgetBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    monthly_limit: Decimal


class GoalBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_amount: Decimal
    target_date: date_ | None
    # Счёт, на котором лежит отложенное, и чем цель закончилась. Ничего из
    # этого в копию не попадало: восстановленная установка возвращала все
    # цели активными и без привязки к счетам, то есть заново резервировала
    # деньги под то, что давно куплено.
    account_id: int | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    closed_at: date_ | None = None


class GoalContributionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_id: int
    amount: Decimal
    date: date_
    note: str | None
    # С какого счёта отложено. Без этого поля восстановление теряет
    # разбивку резерва по счетам, и цель, накопленная с двух карт,
    # возвращается как накопленная ниоткуда.
    account_id: int | None = None
    # Трата, которой цель была реализована.
    transaction_id: int | None = None


class RecurringTransactionBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    category_id: int | None
    transfer_account_id: int | None
    type: TransactionType
    amount: Decimal
    description: str
    merchant: str | None
    notes: str | None
    frequency: RecurringFrequency
    anchor_date: date_
    last_posted_date: date_ | None
    is_active: bool


class AppSettingsBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    # Defaulted so a backup exported before these thresholds existed still
    # imports cleanly under the same format version.
    negative_cash_flow_threshold_months: int = 2
    net_worth_decline_threshold_months: int = 2
    # Defaulted so a backup exported before this threshold existed still
    # imports cleanly under the same format version.
    risky_allocation_threshold_percent: int = 20
    # Defaulted so a backup exported before idle-cash thresholds existed
    # still imports cleanly under the same format version.
    idle_cash_threshold_amount: Decimal = Decimal("1000")
    idle_cash_threshold_days: int = 60
    # С какой даты данным можно доверять. Проставляется при переносе
    # таблицы и отсекает советы по неполной истории.
    reliable_from: date_ | None = None
    # Настройки вида. Их не было в копии вовсе — колонки добавились
    # миграциями после первой версии формата, а сюда их дописать забыли, и
    # восстановление молча возвращало значения по умолчанию. Заметить это
    # можно было бы только по тому, что список операций после
    # восстановления снова открывается на двадцати строках.
    default_dashboard_range: str = "year"
    default_page_size: int = 50
    group_repeats_by_default: bool = True
    day_dividers_by_default: bool = True
    default_account_id: int | None = None
    show_cents: bool = True


# --- Справочники и разделы Aurum-Ex ---
#
# Всё ниже добавлено после первой версии формата и объявлено со значением по
# умолчанию (пустой список). Бэкап, снятый раньше, восстанавливается без
# правки файла и без смены номера формата — ровно та же схема, что уже
# применялась к тегам, разбивкам, бюджетам и целям.
#
# Копия, молча теряющая половину данных, хуже отсутствия копии: она обещает
# безопасность, которой не даёт. Поэтому каждая таблица, появившаяся в
# Aurum-Ex, попадает сюда в том же выпуске, что и сама таблица.


class BankBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None = None
    sort_order: int = 0


class CurrencyBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    symbol: str | None = None
    name: str | None = None
    cbr_nominal: int = 1
    is_active: bool = True


class ExchangeRateBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    rate_date: date_
    rate: Decimal
    published_for: date_ | None = None


class UnitBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: UnitKind
    factor: Decimal = Decimal("1")
    is_base: bool = False
    sort_order: int = 0


class ParticipantBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: ParticipantKind
    color: str | None = None
    is_archived: bool = False


class StoreBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str | None = None
    notes: str | None = None
    is_archived: bool = False


class CounterpartyBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    notes: str | None = None
    is_archived: bool = False


class ProductBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category_id: int | None = None
    unit_id: int | None = None
    barcode: str | None = None
    notes: str | None = None
    is_archived: bool = False


class TransactionItemBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: int
    product_id: int | None = None
    name: str
    category_id: int | None = None
    quantity: Decimal | None = None
    unit_id: int | None = None
    price: Decimal | None = None
    amount: Decimal | None = None
    note: str | None = None
    position: int = 0


class CreditTermsBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    annual_rate_percent: Decimal | None = None
    credit_limit: Decimal | None = None
    grace_days: int | None = None
    payment_day: int | None = None
    minimum_payment: Decimal | None = None
    opened_on: date_ | None = None
    closes_on: date_ | None = None
    notes: str | None = None


class PlanBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None = None
    participant_id: int | None = None
    kind: PlanKind
    amount: Decimal
    currency: str = "RUB"
    valid_from: date_
    valid_to: date_ | None = None
    workdays_only: bool = False
    note: str | None = None
    is_active: bool = True


class WorkPeriodBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    participant_id: int | None = None
    year: int
    month: int
    hours: Decimal = Decimal("0")
    workdays: int | None = None


class InvestmentPortfolioBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None = None
    is_archived: bool = False


class InvestmentHoldingBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    portfolio_id: int
    name: str
    ticker: str | None = None
    kind: InvestmentKind
    currency: str = "RUB"
    external_id: str | None = None
    last_price: Decimal | None = None
    last_price_at: datetime | None = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    notes: str | None = None
    is_archived: bool = False


class InvestmentTradeBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    holding_id: int
    side: TradeSide
    quantity: Decimal
    price_per_unit: Decimal
    fee: Decimal = Decimal("0")
    trade_date: date_
    day_order: int = 0
    account_id: int | None = None
    note: str | None = None


class WidgetBackup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    widget_type: str
    title: str | None = None
    period: str = "current_month"
    row: int = 0
    column: int = 0
    width: int = 1
    config: dict = Field(default_factory=dict)
    is_visible: bool = True


class BackupPayload(BaseModel):
    """A full, portable snapshot of every table. `aurum_backup_version` is
    checked on import so an incompatible/future file is rejected cleanly
    instead of half-applied."""

    aurum_backup_version: int
    exported_at: datetime
    app_version: str
    accounts: list[AccountBackup]
    categories: list[CategoryBackup]
    # Defaulted so a backup exported before tags existed still imports
    # cleanly under the same format version.
    tags: list[TagBackup] = Field(default_factory=list)
    transactions: list[TransactionBackup]
    # Defaulted so a backup exported before transaction splitting existed
    # still imports cleanly under the same format version.
    transaction_splits: list[TransactionSplitBackup] = Field(default_factory=list)
    assets: list[AssetBackup]
    asset_valuations: list[AssetValuationBackup]
    # Defaulted so a backup exported before crypto holdings/portfolios
    # existed still imports cleanly under the same format version.
    crypto_portfolios: list[CryptoPortfolioBackup] = Field(default_factory=list)
    crypto_holdings: list[CryptoHoldingBackup] = Field(default_factory=list)
    crypto_transactions: list[CryptoTransactionBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before budgets existed still imports
    # cleanly under the same format version.
    budgets: list[BudgetBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before goals existed still imports
    # cleanly under the same format version.
    goals: list[GoalBackup] = Field(default_factory=list)
    goal_contributions: list[GoalContributionBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before recurring transactions existed
    # still imports cleanly under the same format version.
    recurring_transactions: list[RecurringTransactionBackup] = Field(default_factory=list)
    # Defaulted so a backup exported before the currency setting existed
    # still imports cleanly under the same format version.
    # Справочники и разделы Aurum-Ex. Все со значением по умолчанию: бэкап,
    # снятый до их появления, восстанавливается без правки файла.
    banks: list[BankBackup] = Field(default_factory=list)
    currencies: list[CurrencyBackup] = Field(default_factory=list)
    exchange_rates: list[ExchangeRateBackup] = Field(default_factory=list)
    units: list[UnitBackup] = Field(default_factory=list)
    participants: list[ParticipantBackup] = Field(default_factory=list)
    stores: list[StoreBackup] = Field(default_factory=list)
    counterparties: list[CounterpartyBackup] = Field(default_factory=list)
    products: list[ProductBackup] = Field(default_factory=list)
    transaction_items: list[TransactionItemBackup] = Field(default_factory=list)
    credit_terms: list[CreditTermsBackup] = Field(default_factory=list)
    plans: list[PlanBackup] = Field(default_factory=list)
    work_periods: list[WorkPeriodBackup] = Field(default_factory=list)
    investment_portfolios: list[InvestmentPortfolioBackup] = Field(default_factory=list)
    investment_holdings: list[InvestmentHoldingBackup] = Field(default_factory=list)
    investment_trades: list[InvestmentTradeBackup] = Field(default_factory=list)
    widgets: list[WidgetBackup] = Field(default_factory=list)
    app_settings: AppSettingsBackup = Field(default_factory=lambda: AppSettingsBackup(currency="USD"))
