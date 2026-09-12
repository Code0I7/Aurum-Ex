"""Валюты и курсы: справочник, загрузка с сайта ЦБ, сводка по капиталу.

Курсы подтягиваются по запросу, а не по расписанию. Причина простая:
приложение одно на одного человека, оно может неделями не открываться, и
фоновая задача, которая всё это время ходит на сайт ЦБ, никому не нужна.
Загрузка запускается, когда её результат кому-то понадобился.
"""
from datetime import date as date_, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.currency import Currency, ExchangeRate
from app.services.cbr_service import CbrUnavailable, sync_rates_for_date
from app.services.currency_service import (
    dates_awaiting_rates,
    get_base_currency,
    get_current_rates,
    recompute_missing_base_amounts,
)

router = APIRouter(prefix="/currencies", tags=["currencies"])

# Сколько дней назад имеет смысл искать курс, если на сегодня его ещё нет.
# Длинные новогодние праздники — самый долгий перерыв в публикации; десяти
# дней хватает с запасом.
MAX_LOOKBACK_DAYS = 10


class CurrencyRead(BaseModel):
    code: str
    symbol: str | None
    name: str | None
    is_active: bool
    # Текущий курс к базовой валюте. У самой базовой всегда 1.
    rate: str | None = None
    rate_date: date_ | None = None


class RateSyncResult(BaseModel):
    saved: int
    rate_date: date_
    message: str
    # Сколько операций удалось досчитать загруженными курсами. Обычно ноль:
    # непересчитанные появляются, только если в день ввода сайт ЦБ был
    # недоступен.
    recomputed: int = 0


class BackfillResult(BaseModel):
    """Итог добора курсов за прошедшие даты."""

    # Дат, за которые ходили на сайт, и сколько курсов из этого сохранилось.
    dates: int
    saved: int
    recomputed: int
    # Осталось дат без курса. Больше нуля — значит, за один раз всё не
    # уместилось и нажать стоит ещё раз.
    remaining: int


@router.get("", response_model=list[CurrencyRead])
async def list_currencies(session: AsyncSession = Depends(get_session)) -> list[CurrencyRead]:
    base = (await get_base_currency(session)).upper()
    currencies = (await session.execute(select(Currency).order_by(Currency.code))).scalars().all()

    # Дата последнего известного курса — по ней видно, насколько свежи
    # цифры, и стоит ли жать «обновить».
    dates = dict(
        (
            await session.execute(
                select(ExchangeRate.code, ExchangeRate.rate_date).order_by(
                    ExchangeRate.code, ExchangeRate.rate_date.desc()
                )
            )
        ).all()
    )
    rates = await get_current_rates(session)

    return [
        CurrencyRead(
            code=currency.code,
            symbol=currency.symbol,
            name=currency.name,
            is_active=currency.is_active,
            rate=str(rates.get(currency.code.upper())) if currency.code.upper() in rates else None,
            rate_date=None if currency.code.upper() == base else dates.get(currency.code),
        )
        for currency in currencies
    ]


@router.post("/rates/sync", response_model=RateSyncResult)
async def sync_rates(
    on_date: date_ | None = Query(default=None, description="Дата курсов; по умолчанию сегодня"),
    session: AsyncSession = Depends(get_session),
) -> RateSyncResult:
    """Загружает курсы с сайта ЦБ.

    Если на запрошенную дату курсов нет — а по выходным и праздникам их не
    публикуют, — отступаем назад по дням до последнего рабочего. Это не
    обходной путь, а нормальный порядок: в выходные и действует курс
    последнего рабочего дня.
    """
    target = on_date or date_.today()

    last_error: str | None = None
    for offset in range(MAX_LOOKBACK_DAYS):
        attempt = target - timedelta(days=offset)
        try:
            saved = await sync_rates_for_date(session, attempt)
        except CbrUnavailable as error:
            last_error = str(error)
            break
        if saved:
            # Загруженные курсы сразу пускаются в дело: операции, которые
            # ждали именно их, досчитываются тем же нажатием.
            recomputed = await recompute_missing_base_amounts(session)
            return RateSyncResult(
                saved=saved, rate_date=attempt, message="ok", recomputed=recomputed
            )

    if last_error:
        # 502, а не 500: сломалась внешняя система, а не приложение.
        raise HTTPException(status_code=502, detail=last_error)

    return RateSyncResult(saved=0, rate_date=target, message="Курсы уже загружены или валют для обновления нет")


# Сколько дат добирать за одно нажатие. Каждая — отдельный поход на сайт ЦБ,
# и сотня дат превратила бы одно нажатие в минуту ожидания. Оставшиеся
# добираются повторным нажатием, и сколько их — сказано в ответе.
MAX_BACKFILL_DATES = 30


@router.post("/rates/backfill", response_model=BackfillResult)
async def backfill_rates(session: AsyncSession = Depends(get_session)) -> BackfillResult:
    """Добирает курсы за даты операций, оставшихся без пересчёта.

    Операция сохраняется даже тогда, когда курса на её дату взять неоткуда —
    потерять запись хуже, чем не знать её курс. Такая операция помечена в
    списке и в итоги не входит, а это нажатие возвращает её в расчёты.

    Курс прошедшего дня не меняется никогда, поэтому добор задним числом не
    переписывает прошлое: он записывает его впервые.
    """
    dates = await dates_awaiting_rates(session, MAX_BACKFILL_DATES)
    saved = 0
    for day in dates:
        try:
            saved += await sync_rates_for_date(session, day)
        except CbrUnavailable:
            # Сайт лёг посреди обхода — то, что успели, уже сохранено, и
            # досчитать по нему стоит. Оставшееся доберётся следующим разом.
            break

    recomputed = await recompute_missing_base_amounts(session)
    remaining = len(await dates_awaiting_rates(session, MAX_BACKFILL_DATES + 1))
    return BackfillResult(
        dates=len(dates), saved=saved, recomputed=recomputed, remaining=remaining
    )
