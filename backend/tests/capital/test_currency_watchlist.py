"""Список наблюдения за курсами.

Справочник валют и есть этот список: строка в нём означает «за курсом этой
валюты я слежу». У рублёвой установки это доллар, евро и юань — их курс
интересен и тому, у кого нет ни одного валютного счёта.

Рядом живёт второй список, и путать их нельзя: валюты, которыми человек
действительно пользуется. Те попадают в блок сами и убраны быть не могут —
их курс нужен расчётам, и перестать его загружать значило бы тихо испортить
итоги.
"""
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import ExchangeRate


async def _rates(client: AsyncClient) -> dict[str, dict]:
    resp = await client.get("/currencies/rates")
    assert resp.status_code == 200, resp.text
    return {row["code"]: row for row in resp.json()}


async def test_a_fresh_install_watches_the_dollar_euro_and_yuan(client: AsyncClient):
    """Блок «Курсы» на пустой установке не должен быть пустым: за этими
    тремя следят все, независимо от своих счетов."""
    rates = await _rates(client)

    assert set(rates) == {"USD", "EUR", "CNY"}


async def test_the_base_currency_is_not_in_the_list(client: AsyncClient):
    """Её курс к самой себе всегда единица, и строка про это отвечает на
    вопрос, которого никто не задавал."""
    assert "RUB" not in await _rates(client)

    resp = await client.post("/currencies", json={"code": "RUB"})
    assert resp.status_code == 400, resp.text


async def test_a_currency_can_be_added_and_removed(client: AsyncClient):
    added = await client.post("/currencies", json={"code": "GBP"})
    assert added.status_code == 201, added.text
    assert "GBP" in await _rates(client)

    removed = await client.delete("/currencies/GBP")
    assert removed.status_code == 204, removed.text
    assert "GBP" not in await _rates(client)


async def test_adding_a_currency_twice_is_not_an_error(client: AsyncClient):
    """Форма присылает код, а не разницу со списком: повторное добавление —
    обычное дело, и падать на нём незачем."""
    assert (await client.post("/currencies", json={"code": "USD"})).status_code == 201
    assert list(await _rates(client)).count("USD") == 1


async def test_the_currency_of_an_account_joins_the_list_by_itself(client: AsyncClient):
    """Курс валюты счёта нужен расчётам — попасть в блок он должен без
    участия человека."""
    resp = await client.post(
        "/accounts", json={"name": "Фунтовая карта", "kind": "checking", "currency": "GBP"}
    )
    assert resp.status_code == 201, resp.text

    rates = await _rates(client)
    assert rates["GBP"]["in_use"] is True


async def test_a_currency_in_use_cannot_be_removed(client: AsyncClient):
    """Перестать загружать её курс значило бы тихо испортить итоги."""
    await client.post("/currencies", json={"code": "GBP"})
    await client.post(
        "/accounts", json={"name": "Фунтовая карта", "kind": "checking", "currency": "GBP"}
    )

    resp = await client.delete("/currencies/GBP")
    assert resp.status_code == 400, resp.text
    assert "GBP" in await _rates(client)


async def test_a_watched_currency_is_not_marked_as_used(client: AsyncClient):
    """За долларом можно следить, не имея ни одного долларового счёта."""
    rates = await _rates(client)

    assert rates["USD"]["in_use"] is False


async def test_without_a_loaded_rate_the_row_is_empty(client: AsyncClient):
    """Валюта в списке есть, курса ещё нет — строка честно пустая, а не с
    единицей на месте неизвестного."""
    rates = await _rates(client)

    assert rates["USD"]["rate"] is None
    assert rates["USD"]["rate_date"] is None
    assert rates["USD"]["previous"] is None


async def test_the_row_shows_the_freshest_rate_and_the_one_before_it(
    client: AsyncClient, session: AsyncSession
):
    """Свежий курс отвечает на вопрос «сколько стоит», предыдущий — на
    «куда движется». Дата предыдущего идёт вместе с ним: курсы хранятся
    только за те дни, когда их грузили, и разница может оказаться не
    дневной."""
    session.add_all(
        [
            ExchangeRate(code="USD", rate_date=date(2026, 3, 4), rate=Decimal("80.0")),
            ExchangeRate(code="USD", rate_date=date(2026, 3, 5), rate=Decimal("81.2")),
            ExchangeRate(code="USD", rate_date=date(2026, 3, 3), rate=Decimal("79.5")),
        ]
    )
    await session.commit()

    row = (await _rates(client))["USD"]

    assert Decimal(row["rate"]) == Decimal("81.2")
    assert row["rate_date"] == "2026-03-05"
    # Предыдущий — именно предыдущий по дате, а не следующая строка в
    # таблице: курсы заводятся не по порядку, добор идёт задним числом.
    assert Decimal(row["previous"]) == Decimal("80.0")
    assert row["previous_date"] == "2026-03-04"


async def test_removing_a_currency_that_is_not_there(client: AsyncClient):
    assert (await client.delete("/currencies/GBP")).status_code == 404
