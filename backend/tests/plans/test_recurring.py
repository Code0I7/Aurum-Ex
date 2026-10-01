"""Регулярные платежи: шаблон, расписание и его сдвиг.

Проверок здесь не было ни одной, а арифметика дат в `_advance` — ровно то
место, где «каждое 31-е число» ломается молча: в феврале такого дня нет, и
решение, что с этим делать, принимает код.

Второе важное свойство: ничего не проводится само. Запись появляется только
по команде, и пропущенная неделя не превращается потом в гору операций,
которых могло и не быть.
"""
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recurring import RecurringTransaction


async def _template(client: AsyncClient, account_id: int, **overrides) -> dict:
    payload = {
        "account_id": account_id,
        "type": "expense",
        "amount": "15.99",
        "description": "Подписка",
        "frequency": "monthly",
        "anchor_date": "2026-01-05",
    }
    payload.update(overrides)
    resp = await client.post("/recurring", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _set_last_posted(session: AsyncSession, recurring_id: int, day: str) -> None:
    """Сдвигает дату последнего проведения напрямую.

    Через API этого не сделать: проведение всегда датируется сегодняшним
    днём, а проверять нужно именно шаг расписания от произвольной даты.
    """
    template = (
        await session.execute(
            select(RecurringTransaction).where(RecurringTransaction.id == recurring_id)
        )
    ).scalar_one()
    template.last_posted_date = date.fromisoformat(day)
    await session.commit()


async def test_a_fresh_template_is_due_on_its_anchor(client: AsyncClient, account_id: int):
    """Пока не проводили ни разу, срок — сама первая дата."""
    template = await _template(client, account_id, anchor_date="2026-01-05")
    assert template["next_due_date"] == "2026-01-05"
    assert template["last_posted_date"] is None


async def test_nothing_posts_on_its_own(client: AsyncClient, account_id: int):
    """Главное свойство: приложение не придумывает операций.

    Пропущенная неделя не должна потом обернуться горой записей, которых
    могло и не быть, — поэтому шаблон только ждёт команды.
    """
    await _template(client, account_id, anchor_date="2020-01-01")
    assert (await client.get("/transactions")).json()["total"] == 0


async def test_posting_creates_a_transaction_dated_today(client: AsyncClient, account_id: int):
    template = await _template(client, account_id, anchor_date="2026-01-05")
    resp = await client.post(f"/recurring/{template['id']}/post")
    assert resp.status_code == 201, resp.text

    today = date.today().isoformat()
    assert resp.json()["last_posted_date"] == today
    page = (await client.get("/transactions")).json()
    assert page["total"] == 1
    assert page["items"][0]["date"] == today
    assert page["items"][0]["description"] == "Подписка"


async def test_posting_a_template_with_a_note_does_not_crash(
    client: AsyncClient, account_id: int
):
    """Заметка на шаблоне не мешает его провести.

    Из-за неё проведение и падало: операция поле notes потеряла, когда
    описание стало необязательным и забрало её роль, а шаблон продолжал
    передавать его в операцию. Пятисотая ошибка на каждое нажатие
    «Провести», и так три недели — потому что у всей этой области не было
    ни одной проверки.
    """
    template = await _template(client, account_id, notes="Списывается пятого")
    resp = await client.post(f"/recurring/{template['id']}/post")
    assert resp.status_code == 201, resp.text
    # Заметка осталась при шаблоне, в операцию не поехала.
    assert (await client.get("/recurring")).json()[0]["notes"] == "Списывается пятого"


async def test_posting_twice_makes_two_transactions(client: AsyncClient, account_id: int):
    """Повтор — законная операция, а не ошибка: платёж бывает и дважды."""
    template = await _template(client, account_id)
    await client.post(f"/recurring/{template['id']}/post")
    await client.post(f"/recurring/{template['id']}/post")
    assert (await client.get("/transactions")).json()["total"] == 2


# --- Шаг расписания -------------------------------------------------------


async def test_the_month_step_lands_on_the_same_day(
    client: AsyncClient, account_id: int, session: AsyncSession
):
    template = await _template(client, account_id, frequency="monthly")
    await _set_last_posted(session, template["id"], "2026-03-15")
    rows = {row["id"]: row for row in (await client.get("/recurring")).json()}
    assert rows[template["id"]]["next_due_date"] == "2026-04-15"


async def test_the_31st_clamps_to_the_end_of_a_shorter_month(
    client: AsyncClient, account_id: int, session: AsyncSession
):
    """«Каждое 31-е» в феврале превращается в последний день февраля.

    Тридцать первого февраля не существует, и выбор здесь между двумя
    неправдами: перепрыгнуть на март — значит пропустить месяц, упасть —
    значит потерять платёж вовсе. Конец месяца ближе к тому, что человек
    имел в виду, когда ставил последнее число.
    """
    template = await _template(client, account_id, frequency="monthly")

    await _set_last_posted(session, template["id"], "2026-01-31")
    rows = {row["id"]: row for row in (await client.get("/recurring")).json()}
    assert rows[template["id"]]["next_due_date"] == "2026-02-28"

    # Апрель короче марта на день — та же развилка, другой месяц.
    await _set_last_posted(session, template["id"], "2026-03-31")
    rows = {row["id"]: row for row in (await client.get("/recurring")).json()}
    assert rows[template["id"]]["next_due_date"] == "2026-04-30"


async def test_the_31st_in_a_leap_february_keeps_the_29th(
    client: AsyncClient, account_id: int, session: AsyncSession
):
    """В високосном году у февраля есть двадцать девятое, и обрезать до
    двадцать восьмого значило бы терять день без причины."""
    template = await _template(client, account_id, frequency="monthly")
    await _set_last_posted(session, template["id"], "2024-01-31")
    rows = {row["id"]: row for row in (await client.get("/recurring")).json()}
    assert rows[template["id"]]["next_due_date"] == "2024-02-29"


async def test_the_month_step_crosses_the_new_year(
    client: AsyncClient, account_id: int, session: AsyncSession
):
    """Декабрь плюс месяц — январь следующего года, а не тринадцатый месяц."""
    template = await _template(client, account_id, frequency="monthly")
    await _set_last_posted(session, template["id"], "2026-12-10")
    rows = {row["id"]: row for row in (await client.get("/recurring")).json()}
    assert rows[template["id"]]["next_due_date"] == "2027-01-10"


async def test_the_week_step_adds_seven_days(
    client: AsyncClient, account_id: int, session: AsyncSession
):
    template = await _template(client, account_id, frequency="weekly")
    await _set_last_posted(session, template["id"], "2026-02-26")
    rows = {row["id"]: row for row in (await client.get("/recurring")).json()}
    # Через конец месяца тоже: неделя не знает про месяцы.
    assert rows[template["id"]]["next_due_date"] == "2026-03-05"


async def test_the_year_step_falls_back_from_february_29(
    client: AsyncClient, account_id: int, session: AsyncSession
):
    """Двадцать девятое февраля бывает раз в четыре года, и ежегодный
    платёж в остальные три приходится на двадцать восьмое."""
    template = await _template(client, account_id, frequency="yearly")
    await _set_last_posted(session, template["id"], "2024-02-29")
    rows = {row["id"]: row for row in (await client.get("/recurring")).json()}
    assert rows[template["id"]]["next_due_date"] == "2025-02-28"


# --- Срок и просрочка -----------------------------------------------------


async def test_a_past_due_date_shows_as_overdue(
    client: AsyncClient, account_id: int, session: AsyncSession
):
    """Дни до срока уходят в минус, а не обнуляются: просрочка на три дня и
    просрочка на год — разные вещи."""
    template = await _template(client, account_id, frequency="weekly")
    await _set_last_posted(session, template["id"], (date.today() - timedelta(days=10)).isoformat())
    rows = {row["id"]: row for row in (await client.get("/recurring")).json()}
    assert rows[template["id"]]["is_due"] is True
    assert rows[template["id"]]["days_until_due"] == -3


async def test_a_future_date_is_not_due_yet(
    client: AsyncClient, account_id: int, session: AsyncSession
):
    template = await _template(client, account_id, frequency="weekly")
    await _set_last_posted(session, template["id"], (date.today() - timedelta(days=2)).isoformat())
    rows = {row["id"]: row for row in (await client.get("/recurring")).json()}
    assert rows[template["id"]]["is_due"] is False
    assert rows[template["id"]]["days_until_due"] == 5


# --- Правка и удаление ----------------------------------------------------


async def test_pausing_a_template_keeps_it(client: AsyncClient, account_id: int):
    """Приостановленный шаблон остаётся: подписку возобновляют чаще, чем
    заводят заново."""
    template = await _template(client, account_id)
    resp = await client.patch(f"/recurring/{template['id']}", json={"is_active": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False
    assert len((await client.get("/recurring")).json()) == 1


async def test_deleting_a_template_leaves_posted_transactions(
    client: AsyncClient, account_id: int
):
    """Проведённое — уже история, и оно не исчезает вместе с шаблоном."""
    template = await _template(client, account_id)
    await client.post(f"/recurring/{template['id']}/post")

    resp = await client.delete(f"/recurring/{template['id']}")
    assert resp.status_code == 204, resp.text
    assert (await client.get("/recurring")).json() == []
    assert (await client.get("/transactions")).json()["total"] == 1


async def test_a_category_of_the_wrong_kind_is_refused(
    client: AsyncClient, account_id: int, categories: dict
):
    """Та же проверка, что у обычной операции: доходная категория в расходе
    означает, что одно из двух выбрано по ошибке."""
    income = next(item for item in categories.values() if item["kind"] == "income")
    resp = await client.post(
        "/recurring",
        json={
            "account_id": account_id,
            "category_id": income["id"],
            "type": "expense",
            "amount": "10.00",
            "description": "Ерунда",
            "frequency": "monthly",
            "anchor_date": "2026-01-05",
        },
    )
    assert resp.status_code == 400, resp.text
