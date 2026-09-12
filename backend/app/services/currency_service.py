"""Перевод сумм в базовую валюту.

Правило, вокруг которого построена вся мультивалютность, простое, но его
две половины смотрят в разные стороны:

* **операция** пересчитывается по курсу того дня, когда она произошла, и
  этот курс копируется в саму запись транзакции. Трата 100 $ в 2022 году
  навсегда остаётся 6 026 ₽ в отчёте за 2022, сколько бы ни стоил доллар
  сегодня — прошлое не переписывается;
* **остаток** на счёте пересчитывается по сегодняшнему курсу: 50 $ стоят
  столько, сколько стоят прямо сейчас.

Здесь живёт первая половина. Вторая появится вместе с загрузкой курсов ЦБ
(этап 5) и переоценкой остатков.

Курс базовой валюты к самой себе всегда ровно 1 и в exchange_rates не
хранится. Это не мелочь: в исходной таблице пара RUBRUB тянулась из
GOOGLEFINANCE и возвращала 0,9999995974, из-за чего каждая сумма
умножалась на почти-единицу и накапливала копеечное расхождение, которое
пользователю приходилось править вручную.
"""
from datetime import date as date_
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.asset import Asset
from app.models.currency import ExchangeRate
from app.models.investment import InvestmentHolding
from app.models.plan import Plan
from app.models.transaction import Transaction
from app.services.settings_service import get_or_create_app_settings

# Точность хранения сумм — два знака, как у Numeric(18, 2) в моделях.
_CENTS = Decimal("0.01")


async def get_base_currency(session: AsyncSession) -> str:
    """Валюта, к которой приводятся все суммы. Живёт в настройках приложения,
    а не в переменной окружения: сменить её после первого запуска — решение
    пользователя, а не администратора сервера."""
    settings = await get_or_create_app_settings(session)
    return settings.currency


async def currencies_in_use(session: AsyncSession) -> set[str]:
    """Валюты, которыми человек действительно пользуется, кроме своей.

    Берутся из самих записей, а не из справочника валют. Справочник — это
    подписи и символы; валюта, в него не попавшая, означала бы молча не
    загруженный курс, то есть доллар, посчитанный по единице, — и ошибку
    видно было бы только по итогам года.

    Плановые суммы считаются наравне с фактическими: план в долларах — это
    обещание, которое тоже надо привести к своей валюте.
    """
    base = (await get_base_currency(session)).upper()
    found: set[str] = set()
    for column in (
        Account.currency,
        Transaction.currency,
        Asset.currency,
        InvestmentHolding.currency,
        Plan.currency,
    ):
        rows = await session.execute(select(column).distinct())
        found.update(code.upper() for (code,) in rows.all() if code)
    found.discard(base)
    return found


async def get_rate(session: AsyncSession, currency: str, on_date: date_) -> Decimal | None:
    """Курс валюты к базовой на указанную дату.

    Возвращает 1 для базовой валюты и None, если курса на эту дату ещё нет
    в базе — загрузка с сайта ЦБ появится на этапе 5. Ближайший более ранний
    курс подходит и сейчас: ЦБ не публикует котировки по выходным и
    праздникам, и в такие дни действует курс последнего рабочего дня.
    """
    base = await get_base_currency(session)
    if currency.upper() == base.upper():
        return Decimal("1")

    stmt = (
        select(ExchangeRate.rate)
        .where(ExchangeRate.code == currency.upper(), ExchangeRate.rate_date <= on_date)
        .order_by(ExchangeRate.rate_date.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def to_base(
    session: AsyncSession,
    amount: Decimal,
    currency: str,
    on_date: date_,
) -> tuple[Decimal, Decimal]:
    """Возвращает пару «курс, сумма в базовой валюте» для записи в транзакцию.

    Если курса на дату нет, берётся 1, а сумма переносится как есть: потерять
    операцию из-за отсутствующей котировки хуже, чем показать её неточно —
    пересчитать потом можно, восстановить незаписанное нельзя.
    """
    rate = await get_rate(session, currency, on_date) or Decimal("1")
    amount_base = (Decimal(amount) * rate).quantize(_CENTS, rounding=ROUND_HALF_UP)
    return rate, amount_base


def quantize_money(amount: Decimal) -> Decimal:
    """Приводит сумму к двум знакам после запятой — тому же виду, в каком
    деньги лежат в базе."""
    return Decimal(amount).quantize(_CENTS, rounding=ROUND_HALF_UP)


async def get_current_rate(session: AsyncSession, currency: str) -> Decimal:
    """Самый свежий известный курс валюты к базовой.

    Для остатков берётся именно он, а не курс на дату операции: 50 долларов
    на счёте стоят столько, сколько стоят сегодня. Курс на дату нужен другой
    половине расчёта — самой операции, и там он заморожен в записи.
    """
    base = await get_base_currency(session)
    if currency.upper() == base.upper():
        return Decimal("1")

    stmt = (
        select(ExchangeRate.rate)
        .where(ExchangeRate.code == currency.upper())
        .order_by(ExchangeRate.rate_date.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() or Decimal("1")


async def get_current_rates(session: AsyncSession) -> dict[str, Decimal]:
    """Свежие курсы всех валют разом — чтобы не ходить в базу на каждый счёт."""
    base = (await get_base_currency(session)).upper()
    rows = (
        await session.execute(
            select(ExchangeRate.code, ExchangeRate.rate, ExchangeRate.rate_date).order_by(
                ExchangeRate.code, ExchangeRate.rate_date.desc()
            )
        )
    ).all()

    rates: dict[str, Decimal] = {base: Decimal("1")}
    for code, rate, _ in rows:
        # Строки отсортированы по дате убыванию, поэтому первая встреченная
        # для каждой валюты и есть самая свежая.
        rates.setdefault(code.upper(), rate)
    return rates


def convert_balance(amount: Decimal, currency: str, rates: dict[str, Decimal]) -> Decimal:
    """Остаток в базовой валюте по текущему курсу.

    Неизвестная валюта считается один к одному, а не отбрасывается: потерять
    счёт в подсчёте капитала хуже, чем показать его неточно, — пропажу
    заметят нескоро, а неверную сумму сразу.
    """
    rate = rates.get(currency.upper(), Decimal("1"))
    return (Decimal(amount) * rate).quantize(_CENTS, rounding=ROUND_HALF_UP)
