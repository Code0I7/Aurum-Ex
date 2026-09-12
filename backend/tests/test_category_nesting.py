"""Вложенность категорий произвольной глубины.

Раньше подкатегория могла быть только одноуровневой: «Продукты → Молочное»
разрешалось, «Продукты → Молочное → Сыр» отклонялось четырёхсотым. Это
наследие оригинального Aurum, и оно мешало разложить накопившийся за годы
список статей по-человечески.

Главное, что здесь проверяется, — не то, что глубокое дерево создаётся, а
то, что деньги доходят по нему до корня. Дерево, в котором сыр не попадает
в продукты, хуже плоского списка: оно выглядит правильным и врёт.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _category(client: AsyncClient, name: str, parent_id: int | None = None, kind: str = "expense") -> dict:
    resp = await client.post(
        "/categories",
        json={"name": name, "kind": kind, "color": "#557799", "parent_id": parent_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _chain(client: AsyncClient, *names: str) -> list[dict]:
    """Заводит цепочку: А → Б → В."""
    made: list[dict] = []
    parent: int | None = None
    for name in names:
        item = await _category(client, name, parent)
        made.append(item)
        parent = item["id"]
    return made


async def _spend(client: AsyncClient, account_id: int, category_id: int, amount: str, date: str = "2026-03-05") -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": amount,
            "description": "Покупка",
            "date": date,
            "category_id": category_id,
        },
    )
    assert resp.status_code == 201, resp.text


async def test_three_levels_can_be_created(client: AsyncClient):
    """А к Б, Б к В — то, что раньше отклонялось."""
    products, dairy, cheese = await _chain(client, "Продукты", "Молочное", "Сыр")
    assert dairy["parent_id"] == products["id"]
    assert cheese["parent_id"] == dairy["id"]


async def test_a_branch_with_children_can_be_moved_whole(client: AsyncClient):
    """Ветку переносят целиком — это и есть «нормальная вложенность»:
    человек раскладывает накопившиеся статьи, не разбирая их по одной."""
    products = await _category(client, "Продукты")
    dairy = await _category(client, "Молочное")
    cheese = await _category(client, "Сыр", dairy["id"])

    resp = await client.patch(f"/categories/{dairy['id']}", json={"parent_id": products["id"]})
    assert resp.status_code == 200, resp.text

    categories = {row["id"]: row for row in (await client.get("/categories")).json()}
    assert categories[dairy["id"]]["parent_id"] == products["id"]
    # Внук уехал вместе с родителем и остался на своём месте в ветке.
    assert categories[cheese["id"]]["parent_id"] == dairy["id"]


async def test_a_category_cannot_be_moved_inside_its_own_subtree(client: AsyncClient):
    """Иначе обе части оторвались бы от корня и пропали из отчётов молча."""
    products, _dairy, cheese = await _chain(client, "Продукты", "Молочное", "Сыр")

    resp = await client.patch(f"/categories/{products['id']}", json={"parent_id": cheese["id"]})
    assert resp.status_code == 400
    resp = await client.patch(f"/categories/{products['id']}", json={"parent_id": products["id"]})
    assert resp.status_code == 400


async def test_income_cannot_nest_under_expense(client: AsyncClient):
    """Одна ветка не может быть наполовину доходной: подъём суммы к корню
    менял бы знак."""
    products = await _category(client, "Продукты", kind="expense")
    resp = await client.post(
        "/categories",
        json={"name": "Кэшбэк", "kind": "income", "color": "#557799", "parent_id": products["id"]},
    )
    assert resp.status_code == 400


async def test_nesting_stops_at_the_depth_limit(client: AsyncClient):
    """Категория седьмого уровня не помещается ни в один список и не
    находится в выпадающем меню."""
    chain = await _chain(client, "У1", "У2", "У3", "У4", "У5")
    assert len(chain) == 5

    resp = await client.post(
        "/categories",
        json={"name": "У6", "kind": "expense", "color": "#557799", "parent_id": chain[-1]["id"]},
    )
    assert resp.status_code == 400


async def test_moving_a_tall_branch_respects_the_limit(client: AsyncClient):
    """Глубина считается по итогу перемещения: ветку из трёх уровней нельзя
    подвесить так, чтобы её низ вышел за предел."""
    deep = await _chain(client, "Г1", "Г2", "Г3")  # ветка высотой 3
    tall = await _chain(client, "В1", "В2", "В3")  # уже три уровня

    # Г1 высотой 3 под В3 (уровень 3) дало бы шесть уровней.
    resp = await client.patch(f"/categories/{deep[0]['id']}", json={"parent_id": tall[2]["id"]})
    assert resp.status_code == 400

    # А под В2 (уровень 2) — ровно пять, что разрешено.
    resp = await client.patch(f"/categories/{deep[0]['id']}", json={"parent_id": tall[1]["id"]})
    assert resp.status_code == 200, resp.text


async def test_spending_on_a_grandchild_reaches_the_root(client: AsyncClient, account_id):
    """Дерево, в котором сыр не попадает в продукты, хуже плоского списка:
    оно выглядит правильным и врёт."""
    products, _dairy, cheese = await _chain(client, "Продукты", "Молочное", "Сыр")
    await _spend(client, account_id, cheese["id"], "450.00")

    dashboard = (await client.get("/dashboard/summary?year=2026&month=3")).json()
    row = next(r for r in dashboard["spending_by_category"] if r["category_id"] == products["id"])
    assert Decimal(row["amount"]) == Decimal("450")


async def test_category_report_folds_in_the_whole_branch(client: AsyncClient, account_id):
    products, dairy, cheese = await _chain(client, "Продукты", "Молочное", "Сыр")
    await _spend(client, account_id, cheese["id"], "450.00")
    await _spend(client, account_id, dairy["id"], "200.00")
    await _spend(client, account_id, products["id"], "100.00")

    report = (await client.get(f"/reports/category-spending?category_id={products['id']}")).json()
    assert Decimal(report["total_amount"]) == Decimal("750")

    # Отчёт по середине ветки видит себя и то, что ниже, но не корень.
    report = (await client.get(f"/reports/category-spending?category_id={dairy['id']}")).json()
    assert Decimal(report["total_amount"]) == Decimal("650")


async def test_budget_on_a_branch_sees_a_grandchild(client: AsyncClient, account_id):
    """Иначе месяц читался бы как 450 потрачено на дашборде и 0 против
    собственного бюджета."""
    products, _dairy, cheese = await _chain(client, "Продукты", "Молочное", "Сыр")
    await client.post("/budgets", json={"category_id": products["id"], "monthly_limit": "10000.00"})
    await _spend(client, account_id, cheese["id"], "450.00")

    status = (await client.get("/budgets/status?year=2026&month=3")).json()
    item = next(row for row in status["items"] if row["category_id"] == products["id"])
    assert Decimal(item["spent"]) == Decimal("450")


async def test_plan_catches_spending_at_the_nearest_ancestor(client: AsyncClient, account_id):
    """План на «Молочном» перехватывает сыр раньше плана на «Продуктах»,
    потому что он ближе.

    Видно это по итогу, а не по строке «Продуктов»: строка родителя
    показывает всю ветку и потому повторяет те же 450. Само правило
    отнесения проверяется тем, что итог остался равен одной трате, а не
    двум, — иначе сыр посчитался бы и в «Молочном», и в «Продуктах».
    """
    products, dairy, cheese = await _chain(client, "Продукты", "Молочное", "Сыр")
    await client.post(
        "/plans",
        json={
            "kind": "month",
            "category_id": products["id"],
            "periods": [{"amount": "20000.00", "valid_from": "2026-01-01"}],
        },
    )
    await client.post(
        "/plans",
        json={
            "kind": "month",
            "category_id": dairy["id"],
            "periods": [{"amount": "3000.00", "valid_from": "2026-01-01"}],
        },
    )
    await _spend(client, account_id, cheese["id"], "450.00")

    overview = (await client.get("/plans/overview?year=2026")).json()
    march = 2
    dairy_row = next(row for row in overview["rows"] if row["name"] == "Молочное")
    products_row = next(row for row in overview["rows"] if row["name"] == "Продукты")
    assert Decimal(dairy_row["months"][march]["actual"]) == Decimal("450")
    # Родитель показывает ту же ветку целиком.
    assert Decimal(products_row["months"][march]["actual"]) == Decimal("450")
    # А в итоге трата ровно одна.
    assert Decimal(overview["expense_totals"][march]["actual"]) == Decimal("450")
