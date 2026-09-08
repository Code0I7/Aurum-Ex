from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AccountKind, AccountNature


class BankBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int = 0


class BankCreate(BankBase):
    pass


class BankUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int | None = None


class BankRead(BankBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class AccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # Renamed from `type` — see models/enums.py, AccountKind.
    kind: AccountKind = AccountKind.CHECKING
    # Optional on input: the service fills it in from `kind` (credit cards
    # and loans become liabilities) unless the user overrides it.
    nature: AccountNature | None = None
    bank_id: int | None = None
    # None означает "как в настройках приложения". Литерала здесь быть не
    # должно: базовую валюту выбирает пользователь, и зашитый в схему код
    # означал бы, что новый счёт молча заводится в чужой валюте.
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    opening_balance: Decimal = Decimal("0")
    opening_date: date_ | None = None
    allow_negative: bool | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: AccountKind | None = None
    nature: AccountNature | None = None
    bank_id: int | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    opening_balance: Decimal | None = None
    opening_date: date_ | None = None
    allow_negative: bool | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_archived: bool | None = None


class AccountRead(AccountBase):
    """Used wherever an account is embedded in another response (e.g.
    TransactionRead.account) — deliberately balance-less so adding a field
    here can never break an unrelated endpoint's serialization."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    # Narrowed from the optional forms above: on the way out these are
    # always resolved.
    nature: AccountNature
    allow_negative: bool
    is_archived: bool
    bank: BankRead | None = None


class AccountWithBalance(AccountRead):
    """The Accounts page's shape — adds the live balance (see
    services/account_service.py), summed from Transaction rows rather than
    stored, the same "derive it" approach net_worth_service.py uses for
    Cash. Used only by /api/accounts' own endpoints, never nested."""

    balance: Decimal
    # Тот же остаток, пересчитанный в базовую валюту по текущему курсу.
    # Для счёта в базовой валюте совпадает с balance — так потребителю не
    # нужна отдельная ветка на «а вдруг валюта та же».
    balance_base: Decimal
