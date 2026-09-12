"""Валюты и курсы: справочник, загрузка с сайта ЦБ, сводка по капиталу.

Курсы подтягиваются по запросу, а не по расписанию. Причина простая:
приложение одно на одного человека, оно может неделями не открываться, и
фоновая задача, которая всё это время ходит на сайт ЦБ, никому не нужна.
Загрузка запускается, когда её результат кому-то понадобился.
"""
from dataclasses import asdict
from datetime import date as date_
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.currency import Currency, ExchangeRate
from app.services.cbr_service import CbrUnavailable, sync_rates_for_date
from app.services.currency_service import (
    currencies_in_use,
    dates_awaiting_rates,
    get_base_currency,
    get_current_rates,
    rate_overview,
    recompute_missing_base_amounts,
)

router = APIRouter(prefix="/currencies", tags=["currencies"])

class CurrencyRead(BaseModel):
    code: str
    symbol: str | None
    name: str | None
    is_active: bool
    # Текущий курс к базовой валюте. У самой базовой всегда 1.
    rate: str | None = None
    rate_date: date_ | None = None


class RateRow(BaseModel):
    """Строка блока «Курсы»."""

    code: str
    rate: Decimal | None = None
    rate_date: date_ | None = None
    previous: Decimal | None = None
    previous_date: date_ | None = None
    # Валютой ведётся счёт или записана операция — значит, курс нужен
    # расчётам, и убрать её из списка нельзя.
    in_use: bool = False


class WatchAdd(BaseModel):
    code: str = Field(min_length=3, max_length=3)


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
    """Загружает курсы с сайта ЦБ на одну дату — и только на неё.

    По выходным и праздникам ЦБ не публикует ничего, и запрос на воскресенье
    возвращает котировки пятницы. Это не обходной путь, а нормальный
    порядок: в выходные и действует пятничный курс. Разбирается с этим сам
    источник, отступать по дням здесь не нужно.

    Раньше отступ был: если на дату ничего не сохранилось, запрос повторялся
    за вчера, позавчера и дальше вглубь. Беда в том, что «ничего не
    сохранилось» означало и «курс на эту дату уже есть»: второе нажатие в
    тот же день уходило за вчера, третье за позавчера — и кнопка
    «обновить» молча набирала историю задним числом. Со стороны это
    выглядело так, будто курсы меняются сами. Для истории есть добор, и он
    ходит ровно по тем датам, которым курса правда не хватает.
    """
    target = on_date or date_.today()

    try:
        saved = await sync_rates_for_date(session, target)
    except CbrUnavailable as error:
        # 502, а не 500: сломалась внешняя система, а не приложение.
        raise HTTPException(status_code=502, detail=str(error)) from error

    # Загруженные курсы сразу пускаются в дело: операции, которые ждали
    # именно их, досчитываются тем же нажатием.
    recomputed = await recompute_missing_base_amounts(session)
    return RateSyncResult(saved=saved, rate_date=target, message="ok", recomputed=recomputed)


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



@router.get("/rates", response_model=list[RateRow])
async def read_rates(session: AsyncSession = Depends(get_session)) -> list[RateRow]:
    """Курсы валют, за которыми следят, и тех, что нужны расчётам."""
    return [RateRow(**asdict(snapshot)) for snapshot in await rate_overview(session)]


@router.post("", response_model=CurrencyRead, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    payload: WatchAdd, session: AsyncSession = Depends(get_session)
) -> CurrencyRead:
    """Добавляет валюту в список наблюдения.

    Курс за неё начнёт загружаться со следующего обновления: набор для
    загрузки складывается из используемых валют и этого списка.
    """
    code = payload.code.upper()
    base = (await get_base_currency(session)).upper()
    if code == base:
        # Курс валюты к самой себе — всегда единица, и строка про это
        # отвечает на вопрос, которого никто не задавал.
        raise HTTPException(status_code=400, detail="Base currency needs no rate")

    currency = await session.get(Currency, code)
    if currency is None:
        currency = Currency(code=code, is_active=True)
        session.add(currency)
    else:
        # Валюта уже была, но отключена — включаем обратно, а не заводим
        # вторую строку с тем же кодом.
        currency.is_active = True
    await session.commit()
    await session.refresh(currency)
    return CurrencyRead(
        code=currency.code,
        symbol=currency.symbol,
        name=currency.name,
        is_active=currency.is_active,
    )


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    code: str, session: AsyncSession = Depends(get_session)
) -> None:
    """Убирает валюту из списка наблюдения.

    Валюту, которой ведётся счёт или записана операция, убрать нельзя: её
    курс нужен расчётам, и перестать его загружать значило бы тихо
    испортить итоги. Сначала нужно разобраться со счётом.
    """
    code = code.upper()
    if code in await currencies_in_use(session):
        raise HTTPException(
            status_code=400, detail="Currency is in use by an account or a transaction"
        )

    currency = await session.get(Currency, code)
    if currency is None:
        raise HTTPException(status_code=404, detail="Currency not found")
    await session.delete(currency)
    await session.commit()
