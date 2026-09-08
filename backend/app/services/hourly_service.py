"""Стоимость покупки в часах работы.

Смысл не в самой ставке, а в переводе трат на язык времени: «этот монитор
стоил мне четыре дня» доходит быстрее, чем «17 273 ₽». Цена в рублях
привычна и потому почти не ощущается; цена в отработанных часах ощущается
сразу.

Ставка считается **по годам**, а не одной цифрой за всё время и не по
месяцам.

Не одной цифрой — потому что за четыре года заработок меняется втрое:
студенческая стипендия и зарплата инженера это разные деньги, и покупка
2022 года по сегодняшней ставке выглядела бы втрое дешевле, чем была.

Не по месяцам — потому что помесячно цифра оказывается шумом. На коротком
окне один месяц даёт копейки за час, а соседний сотни: доход приходит
рывками (аванс, зарплата, подработка попадают в разные месяцы), а часы в
таблице были годовыми и разложены по месяцам поровну. Год усредняет и то и
другое, и именно в такой точности эта цифра и нужна: она отвечает на вопрос
«сколько это в днях работы», а не «сколько ровно».

Год без введённых часов падает на среднюю за всё время. Если часов нет
вовсе, стоимость в часах не показывается — выдумывать ставку хуже, чем
промолчать.
"""
import calendar
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.work_period import WorkPeriod
from app.services.currency_service import quantize_money
from app.services.transaction_service import counted_only


def elapsed_hours(year: int, month: int, hours: Decimal, today: date_ | None = None) -> Decimal:
    """Сколько из введённых на месяц часов уже отработано.

    Часы вводятся на месяц целиком — это план, а не журнал смен. Пока
    месяц идёт, делить доход на весь его план нечестно: первого числа
    получается, что человек заработал за час два рубля, потому что доход у
    него за один день, а часы за тридцать.

    Поэтому у текущего месяца берётся доля по прошедшим дням. Закончившийся
    месяц идёт целиком, ещё не начавшийся — нулём: заработка в нём тоже
    пока нет, и пара «доход и часы» должна описывать один и тот же срок.

    Сегодняшний день считается прошедшим: смену отрабатывают в тот же день,
    когда её записывают.
    """
    today = today or date_.today()
    if (year, month) < (today.year, today.month):
        return hours
    if (year, month) > (today.year, today.month):
        return Decimal("0")
    days_in_month = calendar.monthrange(year, month)[1]
    return hours * Decimal(today.day) / Decimal(days_in_month)


async def get_hourly_rates(session: AsyncSession) -> dict:
    """Ставка за час по годам плюс средняя за всё время.

    Возвращает {"years": {"2026": "255.65", ...}, "overall": "105.01"}.
    Ключ строкой: интерфейс отрезает его от даты операции напрямую, без
    разбора и без часовых поясов.
    """
    # По месяцам, а не суммой по году: у текущего месяца берётся только
    # прошедшая доля, и свернуть это в один SUM на стороне базы нечем.
    hours_rows = (
        await session.execute(select(WorkPeriod.year, WorkPeriod.month, WorkPeriod.hours))
    ).all()
    hours_by_year: dict[int, Decimal] = {}
    for year, month, total in hours_rows:
        if not total:
            continue
        counted = elapsed_hours(int(year), int(month), Decimal(total))
        if counted > 0:
            hours_by_year[int(year)] = hours_by_year.get(int(year), Decimal("0")) + counted

    if not hours_by_year:
        return {"years": {}, "overall": None}

    income_rows = (
        await session.execute(
            select(func.extract("year", Transaction.date), func.sum(Transaction.amount))
            .where(Transaction.type == TransactionType.INCOME, counted_only())
            .group_by(func.extract("year", Transaction.date))
        )
    ).all()
    income_by_year = {int(year): Decimal(total) for year, total in income_rows}

    years: dict[str, str] = {}
    for year, hours in sorted(hours_by_year.items()):
        income = income_by_year.get(year, Decimal("0"))
        if hours > 0 and income > 0:
            years[str(year)] = str(quantize_money(income / hours))

    total_hours = sum(hours_by_year.values(), Decimal("0"))
    # Средняя считается по тем же годам, за которые есть часы: иначе доход
    # года без учёта времени раздул бы ставку, и покупки казались бы дешевле
    # в часах, чем были.
    total_income = sum(
        (amount for year, amount in income_by_year.items() if year in hours_by_year), Decimal("0")
    )
    overall = str(quantize_money(total_income / total_hours)) if total_hours > 0 and total_income > 0 else None

    return {"years": years, "overall": overall}
