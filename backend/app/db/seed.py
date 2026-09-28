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
#
# Только своя. Раньше здесь лежали ещё доллар, евро, юань и бат — «на всякий
# случай», и всякий случай не наступал: в рублёвой установке они годами
# стояли в справочнике, ничего не значили и попадали человеку на глаза как
# намёк, что приложение чего-то от него ждёт. Валюта появляется тогда, когда
# ею действительно платят.
#
# Нулевой курс к самой себе нигде не хранится (см. models/currency.py).
# Список наблюдения на пустой установке: валюты, курс которых интересен и
# тому, у кого нет ни одного валютного счёта. Дальше список принадлежит
# человеку — см. seed_default_currencies.
#
# Названия и символы не заполняются намеренно: подписи валют живут в
# интерфейсе, сразу на двух языках, и вторая их копия здесь разошлась бы с
# первой при первой же правке.
DEFAULT_CURRENCIES: list[tuple[str, str | None, str | None, int]] = [
    ("USD", None, None, 1),
    ("EUR", None, None, 1),
    ("CNY", None, None, 1),
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
# (имя по-русски, имя по-английски, вид, коэффициент к базовой, базовая ли)
#
# Набор метрический и общемировой: галлонов, унций и пинт здесь намеренно
# нет. Это не отказ от них — единицы заводятся руками в справочнике за
# полминуты, — а выбор того, что предлагать по умолчанию: метрическую меру
# поймут везде, а галлон за пределами двух стран читается как загадка.
#
# Имена на двух языках, потому что засев идёт на сервере, а язык до сих пор
# жил только в браузере: до этой пары «кг» и «шт» доставались и тому, кто
# открыл приложение по-английски.
DEFAULT_UNITS = [
    ("кг", "kg", UnitKind.MASS, Decimal("1"), True),
    ("г", "g", UnitKind.MASS, Decimal("0.001"), False),
    ("л", "l", UnitKind.VOLUME, Decimal("1"), True),
    ("мл", "ml", UnitKind.VOLUME, Decimal("0.001"), False),
    ("шт", "pcs", UnitKind.COUNT, Decimal("1"), True),
    ("упак", "pack", UnitKind.COUNT, Decimal("1"), False),
    ("м", "m", UnitKind.LENGTH, Decimal("1"), True),
    ("оплата", "service", UnitKind.SERVICE, Decimal("1"), True),
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
    """Следит, чтобы базовая валюта была в справочнике.

    Установка без собственной валюты — сломанная: все суммы приводятся
    именно к ней.

    Справочник заодно служит списком наблюдения: строка в нём означает «за
    курсом этой валюты я слежу» (см. services/currency_service). Поэтому
    доллар, евро и юань заводятся только на совсем пустой установке —
    дальше список принадлежит человеку, и валюта, убранная им, не должна
    возвращаться при следующем запуске.

    Для расчётов справочник по-прежнему не нужен: курсы загружаются и по
    валютам, которыми человек действительно пользуется, даже если в
    справочник они не попали (см. currencies_in_use)."""
    existing = await session.execute(select(Currency.code))
    known = {code for (code,) in existing.all()}

    if not known:
        for code, symbol, name, nominal in DEFAULT_CURRENCIES:
            session.add(Currency(code=code, symbol=symbol, name=name, cbr_nominal=nominal))
            known.add(code)

    base_code = get_settings().default_currency.upper()
    if base_code not in known:
        session.add(Currency(code=base_code, symbol=None, name=None, cbr_nominal=1))

    await session.commit()


async def seed_default_units(session: AsyncSession, language: str = "ru") -> None:
    """Единицы измерения с коэффициентом приведения к базе своего вида.

    Язык берётся из настроек установки, а на самом первом запуске его ещё
    никто не выбирал — тогда засев идёт по-русски, а выбор на экране
    первичной настройки переименовывает набор (см. rename_default_units).
    Переносить засев целиком на момент настройки нельзя: установка с
    заданным в .env паролем этот экран не показывает вовсе."""
    existing = await session.execute(select(Unit.id).limit(1))
    if existing.first() is not None:
        return

    for order, (name_ru, name_en, kind, factor, is_base) in enumerate(DEFAULT_UNITS):
        name = name_en if language == "en" else name_ru
        session.add(Unit(name=name, kind=kind, factor=factor, is_base=is_base, sort_order=order))

    await session.commit()


async def rename_default_units(session: AsyncSession, language: str) -> int:
    """Переводит стандартные единицы на выбранный язык.

    Переименовывается только то, что совпадает с засеянным именем другого
    языка: «кг» → «kg», но «банка», заведённая человеком, остаётся банкой.
    Ровно то же и с единицей, которую человек переименовал сам, — совпадения
    не будет, и правка переживёт смену языка.

    Возвращает число переименованных строк: вызывающему это нужно только для
    журнала и тестов."""
    names = {
        (name_ru if language == "en" else name_en): (name_en if language == "en" else name_ru)
        for name_ru, name_en, _kind, _factor, _base in DEFAULT_UNITS
    }
    units = (await session.execute(select(Unit))).scalars().all()
    taken = {unit.name for unit in units}
    renamed = 0
    for unit in units:
        replacement = names.get(unit.name)
        # Занятое имя не трогаем: имя единицы уникально, и переименование
        # упало бы на ограничении базы.
        if replacement is None or replacement in taken:
            continue
        taken.discard(unit.name)
        taken.add(replacement)
        unit.name = replacement
        renamed += 1

    if renamed:
        await session.commit()
    return renamed


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
