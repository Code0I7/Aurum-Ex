"""Seeds the default category set on first boot.

The expense categories are assigned hues from the dataviz skill's validated
8-slot categorical palette, in the palette's fixed slot order (never
reordered/cycled) so the dashboard donut chart is colorblind-safe out of the
box. See CLAUDE.md-adjacent design notes in UPDATES.md for the source.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.account import Account
from app.models.category import Category
from app.models.currency import Currency
from app.models.enums import AccountKind, CategoryKind, UnitKind
from app.models.settings import AppSettings
from app.models.unit import Unit

# (code, symbol, name, nominal ЦБ) — валюты, с которых начинается установка.
# Базовая валюта добавляется отдельно из настроек, если её здесь нет: она
# нужна всегда, а остальные — только если человек ими действительно платит.
# Нулевой курс к самой себе нигде не хранится (см. models/currency.py).
DEFAULT_CURRENCIES = [
    ("RUB", "₽", "Российский рубль", 1),
    ("USD", "$", "Доллар США", 1),
    ("EUR", "€", "Евро", 1),
    ("CNY", "¥", "Китайский юань", 1),
    ("THB", "฿", "Таиландский бат", 10),
]

# (name, kind, factor, is_base) — по одной базовой единице на вид измерения.
# Коэффициент приводит к базе: килограмм — это 1000 граммов, литр — 1000
# миллилитров. Без этого «1,5 л за 120 ₽» и «500 мл за 55 ₽» несравнимы, и
# отслеживание цен превращается в угадывание (см. models/unit.py).
# (имя, вид, сколько это базовых, базовая ли)
#
# Базовая мера — та, в которой человек сравнивает цены в магазине:
# килограмм, литр, штука, метр. Грамм и миллилитр в этой роли давали
# «0,074 за миллилитр» — арифметически верно и бесполезно.
DEFAULT_UNITS = [
    ("кг", UnitKind.MASS, Decimal("1"), True),
    ("г", UnitKind.MASS, Decimal("0.001"), False),
    ("л", UnitKind.VOLUME, Decimal("1"), True),
    ("мл", UnitKind.VOLUME, Decimal("0.001"), False),
    ("шт", UnitKind.COUNT, Decimal("1"), True),
    ("упак", UnitKind.COUNT, Decimal("1"), False),
    ("м", UnitKind.LENGTH, Decimal("1"), True),
    ("оплата", UnitKind.SERVICE, Decimal("1"), True),
]

# (name, icon, color) — order doubles as sort_order / palette slot index.
DEFAULT_EXPENSE_CATEGORIES = [
    ("Housing & Utilities", "home", "#2a78d6"),  # slot 1 blue
    ("Groceries", "shopping-basket", "#1baf7a"),  # slot 3 aqua
    ("Dining Out", "utensils", "#eb6834"),  # slot 2 orange
    ("Transportation", "car", "#4a3aa7"),  # slot 7 violet
    ("Health & Fitness", "heart-pulse", "#e34948"),  # slot 8 red
    ("Shopping", "shopping-bag", "#eda100"),  # slot 4 yellow
    ("Entertainment", "clapperboard", "#e87ba4"),  # slot 5 magenta
    ("Subscriptions", "repeat", "#008300"),  # slot 6 green
]

DEFAULT_INCOME_CATEGORIES = [
    ("Salary", "banknote", "#2a78d6"),
    ("Freelance", "briefcase", "#1baf7a"),
    ("Investments", "trending-up", "#4a3aa7"),
    ("Gifts", "gift", "#e87ba4"),
    ("Business Income", "building-2", "#eb6834"),
    ("Rental Income", "key", "#eda100"),
    ("Benefits", "hand-coins", "#008300"),
    ("Item Sales", "tag", "#e34948"),
    ("Other Income", "plus-circle", "#898781"),
]


async def seed_default_categories(session: AsyncSession) -> None:
    existing = await session.execute(select(Category.id).limit(1))
    if existing.first() is not None:
        return

    order = 0
    for name, icon, color in DEFAULT_EXPENSE_CATEGORIES:
        session.add(
            Category(name=name, kind=CategoryKind.EXPENSE, icon=icon, color=color, sort_order=order, is_default=True)
        )
        order += 1
    for name, icon, color in DEFAULT_INCOME_CATEGORIES:
        session.add(
            Category(name=name, kind=CategoryKind.INCOME, icon=icon, color=color, sort_order=order, is_default=True)
        )
        order += 1

    await session.commit()


async def seed_default_currencies(session: AsyncSession) -> None:
    """Заводит список валют и следит, чтобы базовая валюта в нём была.

    Проверка базовой валюты идёт отдельно от общего засева: список могли
    почистить руками, а установка без собственной валюты — сломанная, все
    суммы приводятся именно к ней."""
    existing = await session.execute(select(Currency.code))
    known = {code for (code,) in existing.all()}

    for code, symbol, name, nominal in DEFAULT_CURRENCIES:
        if code not in known:
            session.add(Currency(code=code, symbol=symbol, name=name, cbr_nominal=nominal))
            known.add(code)

    base_code = get_settings().default_currency.upper()
    if base_code not in known:
        session.add(Currency(code=base_code, symbol=None, name=None, cbr_nominal=1))

    await session.commit()


async def seed_default_units(session: AsyncSession) -> None:
    """Единицы измерения с коэффициентом приведения к базе своего вида."""
    existing = await session.execute(select(Unit.id).limit(1))
    if existing.first() is not None:
        return

    for order, (name, kind, factor, is_base) in enumerate(DEFAULT_UNITS):
        session.add(Unit(name=name, kind=kind, factor=factor, is_base=is_base, sort_order=order))

    await session.commit()


async def seed_default_account(session: AsyncSession) -> None:
    """Creates one starter account so the Transactions form always has a
    destination to post to, even before the (future) accounts management UI
    ships."""
    existing = await session.execute(select(Account.id).limit(1))
    if existing.first() is not None:
        return

    session.add(
        Account(
            name="Main Account",
            kind=AccountKind.CHECKING,
            currency=get_settings().default_currency,
            color="#2a78d6",
        )
    )
    await session.commit()


async def seed_default_app_settings(session: AsyncSession) -> None:
    """Ensures the singleton app_settings row (id=1) exists, seeded with
    AURUM_DEFAULT_CURRENCY. The sole place that row gets created — the
    9f3a2d7c5e11 migration only creates the table now, not the row itself
    (an earlier version hardcoded the row to 'USD' at migration time, which
    silently ignored AURUM_DEFAULT_CURRENCY on a fresh install since this
    function's own get-or-create check would find the row already there).
    Runs on every app boot (see main.py's lifespan), so it's also
    self-healing if the row is ever missing (e.g. a DB restored from a
    pre-currency-setting backup)."""
    existing = await session.get(AppSettings, 1)
    if existing is not None:
        return

    session.add(AppSettings(id=1, currency=get_settings().default_currency))
    await session.commit()
