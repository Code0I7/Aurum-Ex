"""Поиск по сумме в той же строке, что и по словам.

Сумму помнят чаще, чем описание. «Что это было за 2 300» — вопрос, с
которого начинается разбор выписки, и до сих пор на него отвечали
пролистыванием месяца глазами.

Целое число ищет рубли, копейки любые: человек, помнящий сумму, помнит её до
рубля, и требовать от него копейки значило бы не находить ничего. Названные
копейки — уточнение, и тогда ищется точно.
"""
from httpx import AsyncClient


async def _spend(client: AsyncClient, account_id: int, amount: str, description: str) -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": amount,
            "description": description,
            "date": "2026-03-05",
        },
    )
    assert resp.status_code == 201, resp.text


async def _found(client: AsyncClient, query: str) -> list[str]:
    resp = await client.get("/transactions", params={"search": query})
    assert resp.status_code == 200, resp.text
    return [row["description"] for row in resp.json()["items"]]


async def test_a_whole_number_finds_the_roubles(client: AsyncClient, account_id: int):
    """1250 находит и 1250,00, и 1250,49 — сумму помнят до рубля."""
    await _spend(client, account_id, "1250.00", "Ровно")
    await _spend(client, account_id, "1250.49", "С копейками")
    await _spend(client, account_id, "1251.00", "Соседняя")

    found = await _found(client, "1250")
    assert sorted(found) == ["Ровно", "С копейками"]


async def test_named_kopecks_search_exactly(client: AsyncClient, account_id: int):
    await _spend(client, account_id, "1250.00", "Ровно")
    await _spend(client, account_id, "1250.49", "С копейками")

    assert await _found(client, "1250.49") == ["С копейками"]
    # Запятая и точка равноправны: на телефоне под рукой одна, на
    # клавиатуре другая.
    assert await _found(client, "1250,49") == ["С копейками"]


async def test_spaces_inside_the_number_are_ignored(client: AsyncClient, account_id: int):
    """Сумму копируют из приложения банка, а там она с разделителем."""
    await _spend(client, account_id, "2300.00", "Из банка")

    assert await _found(client, "2 300") == ["Из банка"]


async def test_words_still_work_and_numbers_do_not_replace_them(
    client: AsyncClient, account_id: int
):
    """Число ищется наравне со словами, а не вместо них: «2300» в описании
    тоже встречается, и выбрасывать такие строки значило бы решать за
    человека, что он имел в виду."""
    await _spend(client, account_id, "2300.00", "Покупка")
    await _spend(client, account_id, "99.00", "Заказ 2300")

    assert sorted(await _found(client, "2300")) == ["Заказ 2300", "Покупка"]


async def test_a_plain_word_search_is_untouched(client: AsyncClient, account_id: int):
    await _spend(client, account_id, "500.00", "Магазин у дома")
    await _spend(client, account_id, "600.00", "Гипермаркет")

    assert await _found(client, "магаз") == ["Магазин у дома"]
