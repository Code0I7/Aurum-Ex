"""История курса: ряд по дням и по месяцам, догрузка с источника.

Раньше курсы лежали в базе только за те дни, когда их загружали: между двумя
нажатиями «обновить» оказывалась неделя, и динамика в блоке «Курсы» была
недельной при дневной подписи. История же не набиралась вовсе — графику
рисовать было нечего.
"""
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import currencies as currency_routes
from app.models.currency import Currency, ExchangeRate
from app.services import cbr_service
from app.services.currency_service import rate_series

# Понедельник 7 сентября 2026 — пятница 11 сентября: ЦБ публикует по рабочим
# дням, выходных 12 и 13 сентября в ответе источника нет вовсе.
WEEK = [
    (date(2026, 9, 7), Decimal("84.10")),
    (date(2026, 9, 8), Decimal("84.20")),
    (date(2026, 9, 9), Decimal("84.30")),
    (date(2026, 9, 10), Decimal("84.40")),
    (date(2026, 9, 11), Decimal("84.50")),
]

DYNAMIC_XML = """<?xml version="1.0" encoding="windows-1251"?>
<ValCurs ID="R01235" DateRange1="07.09.2026" DateRange2="11.09.2026" name="Foreign Currency Dynamic">
  <Record Date="07.09.2026" Id="R01235"><Nominal>1</Nominal><Value>84,1000</Value></Record>
  <Record Date="08.09.2026" Id="R01235"><Nominal>1</Nominal><Value>84,2000</Value></Record>
  <Record Date="09.09.2026" Id="R01235"><Nominal>100</Nominal><Value>8430,0000</Value></Record>
</ValCurs>
"""


async def _store(session: AsyncSession, rows: list[tuple[date, Decimal]]) -> None:
    for rate_date, rate in rows:
        session.add(
            ExchangeRate(code="USD", rate_date=rate_date, rate=rate, published_for=rate_date)
        )
    await session.commit()


def test_history_xml_is_parsed_with_its_own_nominal():
    """Номинал стоит в каждой записи и меняется от года к году: делить надо
    на тот, что в самой записи, а не на сегодняшний."""
    parsed = cbr_service.parse_cbr_history(DYNAMIC_XML)

    assert parsed[date(2026, 9, 7)] == Decimal("84.1")
    # 8430 за сто единиц — это 84,30 за одну.
    assert parsed[date(2026, 9, 9)] == Decimal("84.3")


async def test_weekend_repeats_the_last_published_day(session: AsyncSession):
    """В ряду за неделю семь точек, а не пять: по выходным действует курс
    пятницы, и так его читает всё приложение."""
    await _store(session, WEEK)

    points = await rate_series(session, "USD", date(2026, 9, 7), date(2026, 9, 13))

    assert len(points) == 7
    assert points[-1].date == date(2026, 9, 13)
    assert points[-1].rate == Decimal("84.50")
    assert points[-2].rate == Decimal("84.50")


async def test_monthly_points_take_the_last_rate_of_each_month(session: AsyncSession):
    """«Сколько стоил доллар в конце августа» — вопрос, на который отвечает
    месячная точка."""
    await _store(
        session,
        [
            (date(2026, 7, 31), Decimal("80.00")),
            (date(2026, 8, 14), Decimal("82.00")),
            (date(2026, 8, 31), Decimal("83.00")),
            (date(2026, 9, 11), Decimal("84.50")),
        ],
    )

    points = await rate_series(
        session, "USD", date(2026, 7, 1), date(2026, 9, 15), monthly=True
    )

    assert [(point.date.month, point.rate) for point in points] == [
        (7, Decimal("80.00")),
        (8, Decimal("83.00")),
        (9, Decimal("84.50")),
    ]


async def test_days_before_the_first_known_rate_are_not_drawn(session: AsyncSession):
    """Линия там, где данных нет, — придуманная линия."""
    await _store(session, [(date(2026, 9, 10), Decimal("84.40"))])

    points = await rate_series(session, "USD", date(2026, 9, 7), date(2026, 9, 11))

    assert [point.date for point in points] == [date(2026, 9, 10), date(2026, 9, 11)]


async def test_history_is_loaded_once_and_not_reloaded(session: AsyncSession, monkeypatch):
    """Догрузка идёт одним обращением на валюту, а повторный запрос того же
    периода источник больше не трогает: праздников он не публикует вовсе, и
    «дня не хватает» осталось бы правдой навсегда."""
    calls: list[tuple[date, date]] = []

    async def fake_history(_cbr_code, start, end):
        calls.append((start, end))
        return dict(WEEK)

    # Валюта в справочнике уже есть — засеяна установкой; здесь ей нужен
    # только внутренний код источника.
    usd = await session.get(Currency, "USD")
    if usd is None:
        session.add(Currency(code="USD", cbr_nominal=1, cbr_code="R01235"))
    else:
        usd.cbr_code = "R01235"
    await session.commit()
    monkeypatch.setattr(cbr_service, "fetch_history", fake_history)
    # Память о заданных вопросах живёт в процессе — в тесте начинаем с чистой.
    cbr_service._HISTORY_ASKED.clear()

    saved = await cbr_service.sync_history_if_needed(
        session, "USD", date(2026, 9, 7), date(2026, 9, 11)
    )
    assert saved == len(WEEK)
    assert len(calls) == 1

    again = await cbr_service.sync_history_if_needed(
        session, "USD", date(2026, 9, 7), date(2026, 9, 11)
    )
    assert again == 0
    assert len(calls) == 1


async def test_endpoint_returns_the_series(
    client: AsyncClient, session: AsyncSession, monkeypatch
):
    """Вопрос к приложению один: «покажи курс за период»."""
    await _store(session, WEEK)

    async def no_download(*_args, **_kwargs):
        return 0

    monkeypatch.setattr(currency_routes, "sync_history_if_needed", no_download)

    resp = await client.get(
        "/currencies/USD/history",
        params={"start_date": "2026-09-07", "end_date": "2026-09-11"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "USD"
    assert len(body["points"]) == 5
    assert Decimal(body["points"][0]["rate"]) == Decimal("84.10")
    assert body["source_unavailable"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2026-09-11", "end_date": "2026-09-07"},
        {"start_date": "2024-01-01", "end_date": "2026-09-07"},
    ],
)
async def test_bad_periods_are_refused(client: AsyncClient, params: dict):
    """Перевёрнутый период и период длиннее года: второй источник отдал бы
    тысячи записей, а на графике их всё равно не прочесть."""
    resp = await client.get("/currencies/USD/history", params=params)

    assert resp.status_code == 422
