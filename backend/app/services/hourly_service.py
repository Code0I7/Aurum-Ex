"""Стоимость покупки в часах работы.

Смысл не в самой ставке, а в переводе трат на язык времени: «этот монитор
стоил мне четыре дня» доходит быстрее, чем «17 273 ₽». Цена в рублях
привычна и потому почти не ощущается; цена в отработанных часах ощущается
сразу.

Ставка считается **скользящим окном в три месяца, заканчивающимся месяцем
самой покупки**.

Не одной цифрой за всё время — потому что за четыре года заработок меняется
втрое: студенческая стипендия и зарплата инженера это разные деньги, и
покупка 2022 года по сегодняшней ставке выглядела бы втрое дешевле, чем
была. По той же причине окно привязано к месяцу покупки, а не к сегодня:
трата 2024 года считается по заработку 2024 года.

Не по одному месяцу — потому что помесячно цифра оказывается шумом. На
коротком окне один месяц даёт копейки за час, а соседний сотни: доход
приходит рывками — аванс, зарплата и подработка попадают в разные месяцы, —
а часы вводятся ровным планом. Три месяца этот разрыв закрывают: аванс и
зарплата почти всегда оказываются в одном окне.

Не календарным годом, как было раньше, — потому что у года есть январь.
Первого января окно состояло из одного неполного дня, и до февраля ставка
была бессмысленной. У скользящего окна такого шва нет вовсе. Заодно оно
переживает вахту и перерыв: месяц работы, месяц дома и снова работа
усредняются, а не обнуляют друг друга.

Текущий месяц входит в окно неполной долей — и по часам, и по доходу, —
чтобы пара «доход и часы» описывала один и тот же срок.

Месяц, в окне которого часов нет вовсе, падает на среднюю за всё время.
Если часов нет нигде, стоимость в часах не показывается — выдумывать
ставку хуже, чем промолчать.

Тем же окном считается и **длина рабочего дня** — часы, поделённые на
рабочие дни. Нужна она для перевода часов в дни, и раньше на её месте стояла
константа восемь. Восемь — чужая мерка: у одного человека день 5,5 часа, у
другого 10,5, и «тридцать четыре дня» вместо «двадцати шести» обесценивает
ровно то число, ради которого всё это считается. Доля прошедшего месяца сюда
не применяется: от того, сколько месяца прошло, длина дня не меняется.
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
from app.services.transaction_service import converted_only, counted_only

# Сколько месяцев в окне, включая сам месяц покупки. Три — компромисс:
# одного мало (аванс и зарплата разъезжаются по разным месяцам), год уже
# смазывает рост заработка и упирается в январь.
WINDOW_MONTHS = 3


def _elapsed_fraction(year: int, month: int, today: date_) -> tuple[int, int]:
    """Прошедшая доля месяца дробью: числитель и знаменатель.

    Дробью, а не готовым числом, потому что делить нужно последним.
    Одна тридцатая в десятичной записи не заканчивается, и 300 × (1/30)
    даёт 9,999… вместо десяти — а 300 × 1 / 30 ровно десять. На отработанных
    часах эта разница видна человеку в отчёте.

    Закончившийся месяц — целое, ещё не начавшийся — ноль, текущий — доля по
    прошедшим дням. Сегодняшний день считается прошедшим: смену
    отрабатывают в тот же день, когда её записывают, и без этого первого
    числа доля была бы нулевой, а ставка не считалась бы вовсе.
    """
    if (year, month) < (today.year, today.month):
        return 1, 1
    if (year, month) > (today.year, today.month):
        return 0, 1
    return today.day, calendar.monthrange(year, month)[1]


def elapsed_share(year: int, month: int, today: date_ | None = None) -> Decimal:
    """Какая доля месяца уже прошла: от 0 до 1."""
    numerator, denominator = _elapsed_fraction(year, month, today or date_.today())
    return Decimal(numerator) / Decimal(denominator)


def elapsed_hours(year: int, month: int, hours: Decimal, today: date_ | None = None) -> Decimal:
    """Сколько из введённых на месяц часов уже отработано.

    Часы вводятся на месяц целиком — это план, а не журнал смен. Пока
    месяц идёт, делить доход на весь его план нечестно: первого числа
    получается, что человек заработал за час два рубля, потому что доход у
    него за один день, а часы за тридцать.

    Считается через дробь, а не через готовую долю: см. _elapsed_fraction.
    """
    numerator, denominator = _elapsed_fraction(year, month, today or date_.today())
    return hours * numerator / denominator


def _shift(key: tuple[int, int], back: int) -> tuple[int, int]:
    """Месяц на `back` месяцев раньше данного."""
    year, month = key
    index = year * 12 + (month - 1) - back
    return index // 12, index % 12 + 1


async def get_hourly_rates(session: AsyncSession, today: date_ | None = None) -> dict:
    """Ставка за час по месяцам плюс средняя за всё время.

    Возвращает {"months": {"2026-09": "255.65", ...}, "overall": "105.01"}.
    Ключ строкой «год-месяц»: интерфейс отрезает его от даты операции
    напрямую, без разбора даты и без часовых поясов.
    """
    today = today or date_.today()

    hours_rows = (
        await session.execute(
            select(WorkPeriod.year, WorkPeriod.month, WorkPeriod.hours, WorkPeriod.workdays)
        )
    ).all()
    # Часы месяца — уже с поправкой на прошедшую долю: дальше они только
    # складываются по окну, и незачем помнить, какой из месяцев текущий.
    hours_by_month: dict[tuple[int, int], Decimal] = {}
    # А для длины дня нужны часы как есть, вместе с днями: поправка на
    # прошедшую долю сократилась бы в их отношении, и применять её значило бы
    # делать лишнюю работу с риском ошибиться в одной из двух половин.
    raw_hours: dict[tuple[int, int], Decimal] = {}
    raw_days: dict[tuple[int, int], int] = {}
    for year, month, total, days in hours_rows:
        key = (int(year), int(month))
        if total and days:
            raw_hours[key] = Decimal(total)
            raw_days[key] = int(days)
        if not total:
            continue
        counted = elapsed_hours(int(year), int(month), Decimal(total), today)
        if counted > 0:
            hours_by_month[key] = counted

    if not hours_by_month:
        return {"months": {}, "overall": None, "day_hours": {"months": {}, "overall": None}}

    income_rows = (
        await session.execute(
            select(
                func.extract("year", Transaction.date),
                func.extract("month", Transaction.date),
                # В валюте установки: ставка показывается в ней.
                func.sum(Transaction.amount_base),
            )
            .where(Transaction.type == TransactionType.INCOME, counted_only(), converted_only())
            .group_by(func.extract("year", Transaction.date), func.extract("month", Transaction.date))
        )
    ).all()
    income_by_month = {(int(year), int(month)): Decimal(total) for year, month, total in income_rows}

    # Ставка считается для каждого месяца, где есть хоть часы, хоть доход:
    # покупку показывают в её собственном месяце, а он мог оказаться
    # безработным — тогда его вытянут два предыдущих.
    interesting = set(hours_by_month) | set(income_by_month)
    months: dict[str, str] = {}
    for key in sorted(interesting):
        window = [_shift(key, back) for back in range(WINDOW_MONTHS)]
        hours = sum((hours_by_month.get(m, Decimal("0")) for m in window), Decimal("0"))
        if hours <= 0:
            continue
        # Доход берётся весь, без оглядки на то, введены ли в этом месяце
        # часы. Иначе вахта считалась бы неверно: отработали в марте, а
        # деньги пришли в апреле, когда человек уже отдыхал, — и выкинуть
        # апрельский доход значило бы обнулить заработок за март.
        income = sum((income_by_month.get(m, Decimal("0")) for m in window), Decimal("0"))
        if income <= 0:
            continue
        months[f"{key[0]:04d}-{key[1]:02d}"] = str(quantize_money(income / hours))

    # Длина рабочего дня тем же окном, что и ставка. Отдельным проходом по
    # тем же месяцам: окно у них общее, а условия разные — ставке нужен
    # доход, длине дня он безразличен.
    day_months: dict[str, str] = {}
    for key in sorted(set(raw_days)):
        window = [_shift(key, back) for back in range(WINDOW_MONTHS)]
        window_hours = sum((raw_hours.get(m, Decimal("0")) for m in window), Decimal("0"))
        window_days = sum((raw_days.get(m, 0) for m in window))
        if window_days > 0 and window_hours > 0:
            day_months[f"{key[0]:04d}-{key[1]:02d}"] = str(
                quantize_money(window_hours / window_days)
            )

    all_hours = sum(raw_hours.values(), Decimal("0"))
    all_days = sum(raw_days.values())
    day_overall = str(quantize_money(all_hours / all_days)) if all_days > 0 else None

    total_hours = sum(hours_by_month.values(), Decimal("0"))
    # Средняя считается по тем месяцам, за которые есть часы: иначе доход
    # месяца без учёта времени раздул бы ставку, и покупки казались бы
    # дешевле в часах, чем были.
    total_income = sum(
        (amount for month, amount in income_by_month.items() if month in hours_by_month), Decimal("0")
    )
    overall = str(quantize_money(total_income / total_hours)) if total_hours > 0 and total_income > 0 else None

    return {
        "months": months,
        "overall": overall,
        "day_hours": {"months": day_months, "overall": day_overall},
    }
