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
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.work_period import WorkPeriod
from app.services.currency_service import quantize_money
from app.services.transaction_service import counted_only


async def get_hourly_rates(session: AsyncSession) -> dict:
    """Ставка за час по годам плюс средняя за всё время.

    Возвращает {"years": {"2026": "255.65", ...}, "overall": "105.01"}.
    Ключ строкой: интерфейс отрезает его от даты операции напрямую, без
    разбора и без часовых поясов.
    """
    hours_rows = (
        await session.execute(
            select(WorkPeriod.year, func.sum(WorkPeriod.hours)).group_by(WorkPeriod.year)
        )
    ).all()
    hours_by_year = {int(year): Decimal(total) for year, total in hours_rows if total}

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
