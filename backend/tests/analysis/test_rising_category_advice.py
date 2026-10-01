"""Совет «траты выросли по сравнению со средним».

Среднее считалось делением суммы за три прошлых месяца на три — всегда на
три, даже если категория встречалась в одном из них. Одна покупка на 56 ₽
три месяца назад давала «среднее» 18,67 ₽, и любая обычная трата после неё
выглядела ростом на полторы тысячи процентов. Совет при этом вытеснял
настоящие изменения: он же самый большой по проценту.

Теперь нужна пара месяцев подряд, делится на месяцы с тратами, и рядом с
процентом стоит порог в рублях.
"""
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.advice_service import _rising_category_advice


async def _category(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/categories", json={"name": name, "kind": "expense", "color": "#557799"})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _spend(client: AsyncClient, account_id: int, category_id: int, amount: str, when: date) -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": amount,
            "description": "Покупка",
            "date": when.isoformat(),
            "category_id": category_id,
        },
    )
    assert resp.status_code == 201, resp.text


async def test_a_single_old_purchase_is_not_an_average(
    client: AsyncClient, account_id: int, test_sessionmaker
):
    """Тот самый случай: 56 ₽ один раз в июне и 270 ₽ в сентябре — это не
    рост на 1346%, это просто вторая покупка."""
    category = await _category(client, "Разовое")
    await _spend(client, account_id, category["id"], "56.00", date(2026, 6, 10))
    await _spend(client, account_id, category["id"], "270.00", date(2026, 9, 10))

    async with test_sessionmaker() as session:  # type: AsyncSession
        assert await _rising_category_advice(session, 2026, 9) is None


async def test_two_months_of_history_are_enough(
    client: AsyncClient, account_id: int, test_sessionmaker
):
    """Пара месяцев подряд — уже база для сравнения."""
    category = await _category(client, "Столовая")
    await _spend(client, account_id, category["id"], "3000.00", date(2026, 7, 10))
    await _spend(client, account_id, category["id"], "3000.00", date(2026, 8, 10))
    await _spend(client, account_id, category["id"], "6000.00", date(2026, 9, 10))

    async with test_sessionmaker() as session:  # type: AsyncSession
        advice = await _rising_category_advice(session, 2026, 9)

    assert advice is not None
    assert advice.params["category"] == "Столовая"
    # Среднее по двум месяцам с тратами — 3000, а не 2000 (не делим на три).
    assert advice.params["average"] == 3000.0
    assert advice.params["percent"] == 100


async def test_a_small_rise_in_roubles_is_not_worth_saying(
    client: AsyncClient, account_id: int, test_sessionmaker
):
    """Со 120 ₽ до 200 ₽ — это 67%, но восемьдесят рублей не меняют ни
    одного решения, а место в советах занимают."""
    category = await _category(client, "Мелочь")
    await _spend(client, account_id, category["id"], "120.00", date(2026, 7, 10))
    await _spend(client, account_id, category["id"], "120.00", date(2026, 8, 10))
    await _spend(client, account_id, category["id"], "200.00", date(2026, 9, 10))

    async with test_sessionmaker() as session:  # type: AsyncSession
        assert await _rising_category_advice(session, 2026, 9) is None


async def test_a_real_rise_still_gets_reported(
    client: AsyncClient, account_id: int, test_sessionmaker
):
    """Порог не должен заглушать то, ради чего совет существует."""
    quiet = await _category(client, "Ровная")
    loud = await _category(client, "Выросшая")
    for month in (7, 8):
        await _spend(client, account_id, quiet["id"], "5000.00", date(2026, month, 10))
        await _spend(client, account_id, loud["id"], "2000.00", date(2026, month, 10))
    await _spend(client, account_id, quiet["id"], "5100.00", date(2026, 9, 10))
    await _spend(client, account_id, loud["id"], "8000.00", date(2026, 9, 10))

    async with test_sessionmaker() as session:  # type: AsyncSession
        advice = await _rising_category_advice(session, 2026, 9)

    assert advice is not None
    assert advice.params["category"] == "Выросшая"
