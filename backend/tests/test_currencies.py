"""Курсы валют: разбор ответа ЦБ и переоценка остатков.

Сетевые вызовы здесь не делаются — тесты не должны зависеть от того, жив ли
сайт ЦБ и есть ли на машине интернет. Разбор проверяется на дословном
фрагменте настоящего ответа, а переоценка — на курсах, положенных в базу
напрямую.
"""
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import ExchangeRate
from app.services.cbr_service import CbrUnavailable, parse_cbr_xml, to_base_rates

# Фрагмент настоящего ответа ЦБ. Важны три вещи, которые здесь и
# воспроизведены: кодировка windows-1251, запятая как десятичный разделитель
# и номинал, отличный от единицы.
CBR_SAMPLE = """<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="05.09.2026" name="Foreign Currency Market">
<Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode><Nominal>1</Nominal><Name>Доллар США</Name><Value>86,5379</Value></Valute>
<Valute ID="R01239"><NumCode>978</NumCode><CharCode>EUR</CharCode><Nominal>1</Nominal><Name>Евро</Name><Value>100,5700</Value></Valute>
<Valute ID="R01375"><NumCode>156</NumCode><CharCode>CNY</CharCode><Nominal>10</Nominal><Name>Юаней</Name><Value>128,9435</Value></Valute>
<Valute ID="R01820"><NumCode>392</NumCode><CharCode>JPY</CharCode><Nominal>100</Nominal><Name>Иен</Name><Value>58,7300</Value></Valute>
</ValCurs>"""


def test_rates_are_divided_by_nominal():
    """ЦБ котирует валюту за лот: доллар за 1, юань за 10, иену за 100.
    Без деления на номинал курс завышается в разы, причём молча."""
    rates = parse_cbr_xml(CBR_SAMPLE)

    assert rates["USD"] == Decimal("86.5379")
    assert rates["EUR"] == Decimal("100.5700")
    # 128,9435 за десять юаней — это 12,89435 за один.
    assert rates["CNY"] == Decimal("12.89435")
    # 58,73 за сто иен.
    assert rates["JPY"] == Decimal("0.5873")


def test_broken_xml_raises_a_typed_error():
    """Отдельный тип ошибки нужен, чтобы отличить «внешний сервис лёг» от
    «сломалось приложение»: первое обычное дело, второе требует внимания."""
    with pytest.raises(CbrUnavailable):
        # Незакрытый тег: настоящая страница-заглушка или обрыв ответа
        # выглядят именно так, а не валидным XML с другим содержимым.
        parse_cbr_xml("<html><body>сайт на профилактике")


def test_a_rouble_base_takes_the_quotes_as_they_are():
    """Опорная валюта источника и база установки совпали — делить не на что."""
    quotes = {"USD": Decimal("81.2"), "EUR": Decimal("95.0")}
    assert to_base_rates(quotes, "RUB") == quotes


def test_another_base_gets_cross_rates():
    """Отдельный источник ради долларовой базы не нужен: если рубль даёт
    81,2 за доллар и 95,0 за евро, то евро стоит 95,0 ÷ 81,2 доллара.

    До этого рублёвые котировки легли бы в таблицу под видом долларовых —
    молча и без единого признака ошибки."""
    quotes = {"USD": Decimal("81.2"), "EUR": Decimal("95.0"), "CNY": Decimal("11.4")}

    rates = to_base_rates(quotes, "USD")

    assert "USD" not in rates  # база к самой себе в таблице не хранится
    assert rates["EUR"].quantize(Decimal("0.0001")) == Decimal("1.1700")
    assert rates["CNY"].quantize(Decimal("0.0001")) == Decimal("0.1404")
    # Рубля в ответе ЦБ нет — он и есть единица, — но долларовой
    # установке, держащей рубли, его курс нужен.
    assert rates["RUB"].quantize(Decimal("0.000001")) == Decimal("0.012315")


def test_a_base_the_source_does_not_quote_is_refused():
    """Молча положить единицу тут значит испортить каждую сумму установки."""
    with pytest.raises(CbrUnavailable):
        to_base_rates({"USD": Decimal("81.2")}, "ZWL")

async def test_the_seed_is_the_base_currency_plus_the_watchlist(client: AsyncClient):
    """Справочник стал списком наблюдения: строка в нём означает «за курсом
    этой валюты я слежу».

    Раньше засев клал доллар, евро, юань и бат просто «на всякий случай», и
    в рублёвой установке они годами стояли в справочнике, ничего не значили
    и попадались на глаза как намёк, что приложение чего-то ждёт. Теперь у
    трёх из них появился смысл: их курс показывается на обзоре, и следят за
    ним независимо от своих счетов. Бата среди них нет — он и был лишним.

    Для расчётов справочник по-прежнему ничего не решает: курс валюты счёта
    загрузится и без строки здесь (см. currencies_in_use)."""
    base = (await client.get("/settings")).json()["currency"]

    resp = await client.get("/currencies")
    assert resp.status_code == 200
    assert {row["code"] for row in resp.json()} == {base, "USD", "EUR", "CNY"}


async def test_base_currency_always_has_rate_one(client: AsyncClient):
    """Курс базовой валюты к самой себе жёстко равен 1 и в таблице курсов не
    хранится — иначе внешний источник вернёт почти-единицу, и каждая сумма
    начнёт копить копеечное расхождение."""
    # Базовая валюта берётся из настроек, а не предполагается: она зависит
    # от AURUM_DEFAULT_CURRENCY, и тест, знающий её наизусть, сломается на
    # установке с другой валютой.
    base = (await client.get("/settings")).json()["currency"]

    rows = {row["code"]: row for row in (await client.get("/currencies")).json()}
    assert rows[base]["rate"] == "1"
    assert rows[base]["rate_date"] is None


async def test_balance_is_revalued_at_todays_rate(
    client: AsyncClient, test_sessionmaker
):
    """Остаток на валютном счёте считается по сегодняшнему курсу, в отличие
    от операций, где курс заморожен на дату."""
    base = (await client.get("/settings")).json()["currency"]
    # Валюта счёта должна отличаться от базовой, иначе пересчитывать нечего.
    foreign = "EUR" if base != "EUR" else "USD"

    async with test_sessionmaker() as session:  # type: AsyncSession
        session.add(ExchangeRate(code=foreign, rate_date=date(2026, 9, 5), rate=90))
        await session.commit()

    account = (
        await client.post("/accounts", json={"name": "Валютный", "kind": "savings", "currency": foreign})
    ).json()
    await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "income",
            "amount": "100.00",
            "description": "Перевод",
            "date": "2026-09-05",
            "currency": foreign,
            "category_id": None,
        },
    )

    rows = {row["name"]: row for row in (await client.get("/accounts")).json()}
    # Сотня в валюте счёта — и девять тысяч в базовой по курсу 90.
    assert rows["Валютный"]["balance"] == "100.00"
    assert rows["Валютный"]["balance_base"] == "9000.00"


async def test_rouble_account_reports_the_same_number_twice(client: AsyncClient, account_id):
    """Для счёта в базовой валюте пересчитанный остаток совпадает с обычным —
    так потребителю не нужна отдельная ветка на «а вдруг валюта та же»."""
    rows = (await client.get("/accounts")).json()
    row = next(row for row in rows if row["id"] == account_id)
    assert row["balance"] == row["balance_base"]
