"""Планирование: план разворачивается сам, факт сравнивается с ним.

В исходной таблице «связь 700 ₽» вбивали в двенадцать столбцов руками, а
столовую по 300 ₽ в день умножали в уме — и февраль от января там ничем не
отличался. Здесь проверяется, что записанного один раза достаточно.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _plan(client: AsyncClient, **overrides) -> dict:
    # Сумма и даты переехали в отрезки: у плана их может быть несколько.
    # Помощник продолжает принимать их плоско — тесты вокруг про другое, и
    # заставлять каждый писать список из одного элемента незачем.
    period = {
        "amount": overrides.pop("amount", "700.00"),
        "valid_from": overrides.pop("valid_from", "2026-01-01"),
    }
    if "valid_to" in overrides:
        period["valid_to"] = overrides.pop("valid_to")
    payload = {"kind": "month", "currency": "RUB", "periods": [period]}
    payload.update(overrides)
    resp = await client.post("/plans", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _month(overview: dict, category: str, month: int) -> dict:
    row = next(r for r in overview["rows"] if r["name"] == category)
    return row["months"][month - 1]


async def test_monthly_plan_fills_every_month_from_one_record(client: AsyncClient, categories):
    """Одна запись — двенадцать месяцев. Ради этого всё и затевалось."""
    await _plan(client, category_id=categories["Housing & Utilities"]["id"])

    overview = (await client.get("/plans/overview?year=2026")).json()
    row = next(r for r in overview["rows"] if r["name"] == "Housing & Utilities")
    assert [Decimal(cell["planned"]) for cell in row["months"]] == [Decimal("700")] * 12
    assert Decimal(row["planned_total"]) == Decimal("8400")


async def test_daily_plan_recomputes_february_by_itself(client: AsyncClient, categories):
    """300 ₽ в день — это 9 300 в январе и 8 400 в феврале. Считать это
    руками и значило бы держать в таблице двенадцать разных чисел."""
    await _plan(client, kind="day", amount="300.00", category_id=categories["Dining Out"]["id"])

    overview = (await client.get("/plans/overview?year=2026")).json()
    assert Decimal(_month(overview, "Dining Out", 1)["planned"]) == Decimal("9300")  # 31 день
    assert Decimal(_month(overview, "Dining Out", 2)["planned"]) == Decimal("8400")  # 28 дней
    assert Decimal(_month(overview, "Dining Out", 4)["planned"]) == Decimal("9000")  # 30 дней


async def test_daily_plan_can_count_workdays_instead_of_calendar_days(client: AsyncClient, categories):
    """Рабочая столовая по выходным не работает, и календарные дни завышали
    бы план почти в полтора раза."""
    resp = await client.put("/work-periods", json={"year": 2026, "month": 1, "hours": "160.00", "workdays": 17})
    assert resp.status_code == 200, resp.text

    await _plan(
        client,
        kind="day",
        amount="300.00",
        workdays_only=True,
        category_id=categories["Dining Out"]["id"],
    )

    overview = (await client.get("/plans/overview?year=2026")).json()
    assert Decimal(_month(overview, "Dining Out", 1)["planned"]) == Decimal("5100")  # 17 рабочих дней
    # На февраль отработанных дней не задано — считаем по календарным:
    # лучше приблизительно, чем никак.
    assert Decimal(_month(overview, "Dining Out", 2)["planned"]) == Decimal("8400")


async def test_workdays_only_is_rejected_on_a_non_daily_plan(client: AsyncClient, categories):
    """Галочка, которая ничего не делает, хуже отсутствующей: человек,
    поставивший её, ждал другого поведения."""
    resp = await client.post(
        "/plans",
        json={
            "kind": "month",
            "workdays_only": True,
            "category_id": categories["Housing & Utilities"]["id"],
            "periods": [{"amount": "700.00", "valid_from": "2026-01-01"}],
        },
    )
    assert resp.status_code == 422


async def test_one_off_plan_stands_in_its_own_month_only(client: AsyncClient, categories):
    await _plan(
        client,
        kind="one_off",
        amount="900000.00",
        valid_from="2026-05-01",
        category_id=categories["Transportation"]["id"],
    )

    overview = (await client.get("/plans/overview?year=2026")).json()
    assert Decimal(_month(overview, "Transportation", 5)["planned"]) == Decimal("900000")
    assert Decimal(_month(overview, "Transportation", 4)["planned"]) == Decimal("0")
    assert Decimal(_month(overview, "Transportation", 6)["planned"]) == Decimal("0")


async def test_ending_a_plan_leaves_the_past_untouched(client: AsyncClient, categories):
    """План прекращают датой, а не удалением: прошлое сравнение «план —
    факт» должно остаться правдой."""
    plan = await _plan(client, category_id=categories["Housing & Utilities"]["id"])
    # Отрезки присылаются целиком: список в форме виден весь, и «дополнить»
    # означало бы, что удалённую строку нельзя удалить.
    await client.patch(
        f"/plans/{plan['id']}",
        json={"periods": [{"amount": "700.00", "valid_from": "2026-01-01", "valid_to": "2026-06-30"}]},
    )

    overview = (await client.get("/plans/overview?year=2026")).json()
    assert Decimal(_month(overview, "Housing & Utilities", 6)["planned"]) == Decimal("700")
    assert Decimal(_month(overview, "Housing & Utilities", 7)["planned"]) == Decimal("0")


async def test_actual_is_compared_against_the_plan(client: AsyncClient, account_id, categories):
    await _plan(client, category_id=categories["Housing & Utilities"]["id"])
    await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "820.00",
            "description": "Связь",
            "date": "2026-03-05",
            "category_id": categories["Housing & Utilities"]["id"],
        },
    )

    overview = (await client.get("/plans/overview?year=2026")).json()
    march = _month(overview, "Housing & Utilities", 3)
    assert Decimal(march["planned"]) == Decimal("700")
    assert Decimal(march["actual"]) == Decimal("820")
    assert Decimal(march["deviation"]) == Decimal("120")


async def test_spending_on_a_subcategory_counts_towards_the_branch_plan(
    client: AsyncClient, account_id, categories
):
    """План ставят на ветку, а тратят по листьям. Сравнивать ветку только с
    тем, что записано прямо в неё, значило бы показать нулевой факт при
    полном холодильнике."""
    groceries = categories["Groceries"]["id"]
    child = (
        await client.post(
            "/categories", json={"name": "Молочное", "kind": "expense", "color": "#889911", "parent_id": groceries}
        )
    ).json()
    await _plan(client, amount="20000.00", category_id=groceries)
    await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "1500.00",
            "description": "Молоко",
            "date": "2026-02-10",
            "category_id": child["id"],
        },
    )

    overview = (await client.get("/plans/overview?year=2026")).json()
    february = _month(overview, "Groceries", 2)
    assert Decimal(february["actual"]) == Decimal("1500")
    assert Decimal(february["planned"]) == Decimal("20000")


async def test_unplanned_spending_still_appears(client: AsyncClient, account_id, categories):
    """Незапланированная трата — ровно то, что планирование должно
    показывать, поэтому строка без плана из таблицы не исчезает."""
    await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "4000.00",
            "description": "Внезапно",
            "date": "2026-08-01",
            "category_id": categories["Entertainment"]["id"],
        },
    )

    overview = (await client.get("/plans/overview?year=2026")).json()
    august = _month(overview, "Entertainment", 8)
    assert Decimal(august["planned"]) == Decimal("0")
    assert Decimal(august["actual"]) == Decimal("4000")


async def test_totals_split_income_from_expense_and_give_free_funds(
    client: AsyncClient, account_id, categories
):
    """Три итоговые полосы: пришло, ушло, осталось — и по плану, и по
    факту."""
    await _plan(client, amount="40000.00", category_id=categories["Salary"]["id"])
    await _plan(client, amount="700.00", category_id=categories["Housing & Utilities"]["id"])
    await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "income",
            "amount": "45000.00",
            "description": "Зарплата",
            "date": "2026-01-10",
            "category_id": categories["Salary"]["id"],
        },
    )

    overview = (await client.get("/plans/overview?year=2026")).json()
    assert Decimal(overview["income_totals"][0]["planned"]) == Decimal("40000")
    assert Decimal(overview["income_totals"][0]["actual"]) == Decimal("45000")
    assert Decimal(overview["expense_totals"][0]["planned"]) == Decimal("700")
    assert Decimal(overview["free_totals"][0]["planned"]) == Decimal("39300")
    assert Decimal(overview["free_totals"][0]["actual"]) == Decimal("45000")


async def test_several_plans_on_one_category_add_up(client: AsyncClient, categories):
    """«Связь 700» и «интернет 500» — две записи, а строка в таблице одна."""
    utilities = categories["Housing & Utilities"]["id"]
    await _plan(client, amount="700.00", category_id=utilities, note="Связь")
    await _plan(client, amount="500.00", category_id=utilities, note="Интернет")

    overview = (await client.get("/plans/overview?year=2026")).json()
    assert Decimal(_month(overview, "Housing & Utilities", 1)["planned"]) == Decimal("1200")


async def test_valid_to_before_valid_from_is_rejected(client: AsyncClient):
    resp = await client.post(
        "/plans",
        json={
            "kind": "month",
            "periods": [{"amount": "700.00", "valid_from": "2026-06-01", "valid_to": "2026-01-01"}],
        },
    )
    assert resp.status_code == 422


async def test_a_row_carries_its_path_and_its_depth(
    client: AsyncClient, account_id, categories
):
    """План на подкатегории встаёт в таблицу рядом с корневыми строками.

    Без пути «Иван» ничего не говорит о том, чей это доход и где он
    лежит, — а имена подкатегорий не уникальны.

    Глубина отдаётся отдельно: в самой строке стоит короткое имя с
    отступом по ней, как на вкладке категорий, а путь остаётся подсказкой
    при наведении.
    """
    salary = categories["Salary"]["id"]
    ivan = (
        await client.post(
            "/categories",
            json={"name": "Иван", "kind": "income", "color": "#2a78d6", "parent_id": salary},
        )
    ).json()
    assert (
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "type": "income",
                "amount": "200000.00",
                "description": "Зарплата",
                "date": "2026-01-10",
                "category_id": ivan["id"],
            },
        )
    ).status_code == 201

    # Пока плана нет — строка есть, но помечена как «только факт».
    before = (await client.get("/plans/overview", params={"year": 2026})).json()
    row = next(item for item in before["rows"] if item["category_id"] == salary)
    assert row["path"] == "Salary"
    assert row["depth"] == 0

    assert (
        await client.post(
            "/plans",
            json={
                "category_id": ivan["id"],
                "kind": "month",
                "periods": [{"amount": "200000.00", "valid_from": "2026-01-01"}],
            },
        )
    ).status_code == 201

    after = (await client.get("/plans/overview", params={"year": 2026})).json()
    planned = next(item for item in after["rows"] if item["category_id"] == ivan["id"])
    assert planned["path"] == "Salary · Иван"
    assert planned["depth"] == 1
    # В строке — короткое имя: путь целиком в узкой колонке обрезается ровно
    # на том конце, который и нужен.
    assert planned["name"] == "Иван"


async def test_a_plan_on_an_income_subcategory_does_not_flip_the_totals(
    client: AsyncClient, account_id, categories
):
    """Доход остаётся доходом на любой глубине.

    Проверка написана после жалобы «добавил в план подкатегорию из доходов,
    получил минус»: арифметика оказалась верной, но закрепить её стоит —
    подкатегория дохода не должна ни уходить в расходную половину, ни
    менять свободные средства.
    """
    salary = categories["Salary"]["id"]
    ivan = (
        await client.post(
            "/categories",
            json={"name": "Иван", "kind": "income", "color": "#2a78d6", "parent_id": salary},
        )
    ).json()
    await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "income",
            "amount": "200000.00",
            "description": "Зарплата",
            "date": "2026-01-10",
            "category_id": ivan["id"],
        },
    )
    await client.post(
        "/plans",
        json={
            "category_id": ivan["id"],
            "kind": "month",
            "periods": [{"amount": "200000.00", "valid_from": "2026-01-01"}],
        },
    )

    body = (await client.get("/plans/overview", params={"year": 2026})).json()
    january = 0
    assert Decimal(body["income_totals"][january]["actual"]) == Decimal("200000.00")
    assert Decimal(body["income_totals"][january]["planned"]) == Decimal("200000.00")
    assert Decimal(body["expense_totals"][january]["actual"]) == Decimal("0")
    assert Decimal(body["free_totals"][january]["actual"]) == Decimal("200000.00")


async def test_a_parent_row_shows_its_whole_branch(client: AsyncClient, account_id, categories):
    """План стоит на «Администрации», а «Иван» над ней выглядел пустым.

    Деньги в ветке есть — просто строкой ниже: строки держат только то, что
    отнесено лично к ним, и весь факт уходил в ту строку, у которой план.
    Дашборд и отчёты в такой ситуации сворачивают ветку, и здесь человек
    ждёт того же.
    """
    salary = categories["Salary"]["id"]
    ivan = (
        await client.post(
            "/categories",
            json={"name": "Иван", "kind": "income", "color": "#2a78d6", "parent_id": salary},
        )
    ).json()
    admin = (
        await client.post(
            "/categories",
            json={"name": "Администрация", "kind": "income", "color": "#2a78d6", "parent_id": ivan["id"]},
        )
    ).json()

    await client.post(
        "/plans",
        json={
            "category_id": admin["id"],
            "kind": "month",
            "periods": [{"amount": "20000.00", "valid_from": "2026-01-01"}],
        },
    )
    assert (
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "type": "income",
                "amount": "31480.55",
                "description": "Зарплата",
                "date": "2026-08-14",
                "category_id": admin["id"],
            },
        )
    ).status_code == 201

    body = (await client.get("/plans/overview", params={"year": 2026})).json()
    rows = {item["category_id"]: item for item in body["rows"]}
    august = 7

    # Ребёнок держит своё.
    assert Decimal(rows[admin["id"]]["months"][august]["actual"]) == Decimal("31480.55")
    # Родитель и прародитель показывают ту же ветку, а не прочерк.
    assert Decimal(rows[ivan["id"]]["months"][august]["actual"]) == Decimal("31480.55")
    assert Decimal(rows[salary]["months"][august]["actual"]) == Decimal("31480.55")
    assert Decimal(rows[ivan["id"]]["months"][august]["planned"]) == Decimal("20000.00")


async def test_the_totals_are_not_doubled_by_the_rollup(client: AsyncClient, account_id, categories):
    """Главное, чем платят за сворачивание: итог обязан остаться верным.

    Родитель и ребёнок показывают одни и те же деньги, поэтому итоговые
    полосы считаются до сворачивания — по непересекающимся суммам.
    """
    salary = categories["Salary"]["id"]
    ivan = (
        await client.post(
            "/categories",
            json={"name": "Иван", "kind": "income", "color": "#2a78d6", "parent_id": salary},
        )
    ).json()
    await client.post(
        "/plans",
        json={
            "category_id": ivan["id"],
            "kind": "month",
            "periods": [{"amount": "20000.00", "valid_from": "2026-01-01"}],
        },
    )
    await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "income",
            "amount": "31480.55",
            "description": "Зарплата",
            "date": "2026-08-14",
            "category_id": ivan["id"],
        },
    )

    body = (await client.get("/plans/overview", params={"year": 2026})).json()
    august = 7
    assert Decimal(body["income_totals"][august]["actual"]) == Decimal("31480.55")
    assert Decimal(body["income_totals"][august]["planned"]) == Decimal("20000.00")
    assert Decimal(body["free_totals"][august]["actual"]) == Decimal("31480.55")
