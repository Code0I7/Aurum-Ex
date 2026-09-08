"""Схема чтения обязана показывать всё, что лежит в базе.

Проверка от настоящего сбоя. Перенос таблицы принёс три операции с нулевой
суммой — строки, где сумму в исходном листе просто не проставили, вроде
«Корректировка» и «Перевод брату». Схема чтения наследовала от схемы ввода
ограничение «сумма больше нуля», и вкладка операций отвечала пятисоткой на
весь месяц, в котором такая строка нашлась. Починить её можно было только
через интерфейс, который из-за неё же и не открывался.

Ограничения ввода остаются на вводе: записать нулевую сумму через
приложение по-прежнему нельзя.
"""
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.enums import TransactionType
from app.models.transaction import Transaction, TransactionItem
from tests.helpers import txn_payload


async def test_zero_amount_row_does_not_take_the_whole_month_down(
    client: AsyncClient, test_sessionmaker, account_id
):
    """Строка пишется в обход API — ровно так её и заводит перенос
    таблицы, который создаёт объекты модели напрямую."""
    await client.post("/transactions", json=txn_payload(account_id, amount="100.00", date="2026-04-05"))
    async with test_sessionmaker() as session:
        session.add(
            Transaction(
                account_id=account_id,
                type=TransactionType.EXPENSE,
                amount=Decimal("0.00"),
                description="Корректировка",
                date=date(2026, 4, 27),
                currency="RUB",
                # Сумма в базовой валюте заполняется маршрутом; при записи
                # в обход него её нужно проставить руками — как это делает
                # и перенос таблицы.
                amount_base=Decimal("0.00"),
            )
        )
        await session.commit()

    resp = await client.get("/transactions?year=2026&month=4")
    assert resp.status_code == 200, resp.text
    descriptions = [item["description"] for item in resp.json()["items"]]
    # Обе строки на месте: и обычная, и та, из-за которой всё падало.
    assert "Корректировка" in descriptions
    assert len(descriptions) == 2


async def test_zero_quantity_item_does_not_take_the_list_down(
    client: AsyncClient, test_sessionmaker, account_id
):
    """То же и у позиции чека: нулевое количество из перенесённой таблицы
    роняло бы весь список, а не только свою строку."""
    created = (
        await client.post("/transactions", json=txn_payload(account_id, amount="100.00", date="2026-04-05"))
    ).json()
    async with test_sessionmaker() as session:
        session.add(
            TransactionItem(
                transaction_id=created["id"],
                name="Пакет",
                quantity=Decimal("0"),
                position=0,
            )
        )
        await session.commit()

    resp = await client.get("/transactions?year=2026&month=4")
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("amount", ["0.00", "-10.00"])
async def test_writing_such_a_row_through_the_app_is_still_refused(
    client: AsyncClient, account_id, amount
):
    """Терпимость на чтении не означает терпимости на записи: заводить
    новые нулевые строки приложение по-прежнему не даёт."""
    resp = await client.post("/transactions", json=txn_payload(account_id, amount=amount))
    assert resp.status_code == 422


async def test_transaction_without_description_is_accepted(client: AsyncClient, account_id):
    """Описание необязательно: в исходной таблице это была вторая строка
    записи, а не заметка, и у большинства покупок сказать сверх категории
    нечего. Требовать текст значит заставлять придумывать «Продукты» и
    «Покупка» — описания хуже пустых, потому что выглядят содержательными.
    """
    payload = txn_payload(account_id, amount="100.00")
    payload.pop("description")
    resp = await client.post("/transactions", json=payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["description"] is None


async def test_blank_description_is_stored_as_absent(client: AsyncClient, account_id):
    """Пустая строка приходит из формы, где поле просто не заполнили.
    Хранить её отдельно от «не задано» незачем: в списке они выглядят
    одинаково, а в проверках расходятся."""
    resp = await client.post(
        "/transactions", json=txn_payload(account_id, amount="100.00", description="   ")
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["description"] is None
