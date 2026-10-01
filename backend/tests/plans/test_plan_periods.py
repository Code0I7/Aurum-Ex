"""У плана несколько отрезков вместо одной суммы.

Сумма и даты жили прямо в плане, и смена тарифа означала второй план: та же
категория, тот же вид, другая сумма, другие даты. За несколько лет от
«связи 700 ₽» оставался десяток записей с одинаковым названием, и понять,
какая действует сейчас, можно было только сверив даты у всех.

Теперь план — это категория и способ счёта, а суммы лежат внутри списком.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _category(client: AsyncClient, name: str = "Связь") -> dict:
    resp = await client.post("/categories", json={"name": name, "kind": "expense", "color": "#557799"})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _plan(client: AsyncClient, category_id: int, periods: list[dict], **extra) -> dict:
    resp = await client.post(
        "/plans",
        json={"category_id": category_id, "kind": "month", "periods": periods, **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _month(overview: dict, category_id: int, month: int) -> Decimal:
    row = next(item for item in overview["rows"] if item["category_id"] == category_id)
    return Decimal(row["months"][month - 1]["planned"])


async def test_the_tariff_changes_inside_one_plan(client: AsyncClient):
    """Ради этого всё и затевалось: 700 до июня, 900 после — одна запись."""
    category = await _category(client)
    await _plan(
        client,
        category["id"],
        [
            {"amount": "700.00", "valid_from": "2026-01-01", "valid_to": "2026-05-31"},
            {"amount": "900.00", "valid_from": "2026-06-01", "note": "подорожал тариф"},
        ],
    )

    overview = (await client.get("/plans/overview?year=2026")).json()
    assert _month(overview, category["id"], 3) == Decimal("700.00")
    assert _month(overview, category["id"], 5) == Decimal("700.00")
    assert _month(overview, category["id"], 6) == Decimal("900.00")
    assert _month(overview, category["id"], 12) == Decimal("900.00")


async def test_a_month_between_periods_is_empty(client: AsyncClient):
    """Разрыв — это «в эти месяцы плана нет», а не «продолжается прошлый».
    Молча растягивать предыдущую сумму значило бы придумывать план, которого
    человек не ставил."""
    category = await _category(client)
    await _plan(
        client,
        category["id"],
        [
            {"amount": "700.00", "valid_from": "2026-01-01", "valid_to": "2026-02-28"},
            {"amount": "900.00", "valid_from": "2026-05-01"},
        ],
    )

    overview = (await client.get("/plans/overview?year=2026")).json()
    assert _month(overview, category["id"], 2) == Decimal("700.00")
    assert _month(overview, category["id"], 3) == Decimal("0")
    assert _month(overview, category["id"], 5) == Decimal("900.00")


async def test_overlapping_periods_are_rejected(client: AsyncClient):
    """На один месяц приложение обязано знать одну сумму. Выбрать за
    человека, какая из двух главнее, — соврать в таблице года, причём
    молча и правдоподобно."""
    category = await _category(client)
    resp = await client.post(
        "/plans",
        json={
            "category_id": category["id"],
            "kind": "month",
            "periods": [
                {"amount": "700.00", "valid_from": "2026-01-01", "valid_to": "2026-06-30"},
                {"amount": "900.00", "valid_from": "2026-05-01"},
            ],
        },
    )
    assert resp.status_code == 422, resp.text


async def test_an_open_period_must_be_the_last(client: AsyncClient):
    """Отрезок без конца уходит в бесконечность и перекрывает всё, что за
    ним: это тот же перехлёст, просто записанный иначе."""
    category = await _category(client)
    resp = await client.post(
        "/plans",
        json={
            "category_id": category["id"],
            "kind": "month",
            "periods": [
                {"amount": "700.00", "valid_from": "2026-01-01"},
                {"amount": "900.00", "valid_from": "2026-06-01"},
            ],
        },
    )
    assert resp.status_code == 422, resp.text


async def test_a_plan_without_periods_is_rejected(client: AsyncClient):
    """План без сумм — это категория, отмеченная галочкой, и в таблице года
    он даёт пустую строку."""
    category = await _category(client)
    resp = await client.post(
        "/plans", json={"category_id": category["id"], "kind": "month", "periods": []}
    )
    assert resp.status_code == 422, resp.text


async def test_periods_are_replaced_whole_on_update(client: AsyncClient):
    """Правка приходит из формы, где список виден весь. «Дополнить» означало
    бы, что удалённую строку нельзя удалить."""
    category = await _category(client)
    plan = await _plan(
        client,
        category["id"],
        [
            {"amount": "700.00", "valid_from": "2026-01-01", "valid_to": "2026-05-31"},
            {"amount": "900.00", "valid_from": "2026-06-01"},
        ],
    )
    assert len(plan["periods"]) == 2

    resp = await client.patch(
        f"/plans/{plan['id']}",
        json={"periods": [{"amount": "800.00", "valid_from": "2026-01-01"}]},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["periods"]) == 1

    overview = (await client.get("/plans/overview?year=2026")).json()
    assert _month(overview, category["id"], 7) == Decimal("800.00")


async def test_the_note_explains_the_change(client: AsyncClient):
    """Через год «почему тут 900» — вопрос, на который иначе не ответит
    никто."""
    category = await _category(client)
    plan = await _plan(
        client,
        category["id"],
        [
            {"amount": "700.00", "valid_from": "2026-01-01", "valid_to": "2026-05-31"},
            {"amount": "900.00", "valid_from": "2026-06-01", "note": "сменил оператора"},
        ],
    )
    notes = [period["note"] for period in plan["periods"]]
    assert notes == [None, "сменил оператора"]


async def test_a_daily_plan_changes_rate_mid_year(client: AsyncClient):
    """Отрезки работают и с ежедневным планом: умножается сумма того
    отрезка, который действует в месяце."""
    category = await _category(client, "Столовая")
    await _plan(
        client,
        category["id"],
        [
            {"amount": "200.00", "valid_from": "2026-01-01", "valid_to": "2026-01-31"},
            {"amount": "300.00", "valid_from": "2026-02-01"},
        ],
        kind="day",
    )

    overview = (await client.get("/plans/overview?year=2026")).json()
    # Январь — 31 день по 200, февраль — 28 по 300.
    assert _month(overview, category["id"], 1) == Decimal("6200.00")
    assert _month(overview, category["id"], 2) == Decimal("8400.00")


async def test_deleting_the_plan_takes_its_periods(client: AsyncClient):
    category = await _category(client)
    plan = await _plan(client, category["id"], [{"amount": "700.00", "valid_from": "2026-01-01"}])

    assert (await client.delete(f"/plans/{plan['id']}")).status_code == 204
    assert (await client.get("/plans")).json() == []
