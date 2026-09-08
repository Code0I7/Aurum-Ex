"""Автоматическая раскладка категорий.

Две ступени разного качества, и проверяются они по-разному. Раскладка по
общему началу имени — это чтение того, что человек уже написал, и она
обязана быть точной. Раскладка по смыслу — догадка, и от неё требуется
осторожность: лишний уровень, который потом разбирать руками, хуже плоского
списка.
"""
from httpx import AsyncClient

from app.services.category_grouping import build_nesting, group_by_meaning, group_by_shared_prefix, split_prefix


def test_a_dash_in_the_name_is_read_as_hierarchy():
    assert split_prefix("Электроника - Аксессуары") == ("Электроника", "Аксессуары")
    assert split_prefix("Электроника — Комплектующие") == ("Электроника", "Комплектующие")
    # Ни то ни другое не иерархия: «18+» разделителя не содержит, а тире без
    # пробелов — часть слова.
    assert split_prefix("18+") is None
    assert split_prefix("Кофе-брейк") is None
    # Половинки-пустышки — опечатка, а не структура.
    assert split_prefix(" - Прочее") is None


def test_branches_with_a_shared_beginning_get_one_parent():
    """Человек уже назвал их одинаково — остаётся прочитать."""
    assignment = group_by_shared_prefix(["Электроника - Аксессуары", "Электроника - Комплектующие", "Мебель"])
    assert assignment == {
        "Электроника - Аксессуары": "Электроника",
        "Электроника - Комплектующие": "Электроника",
    }


def test_a_lone_branch_gets_no_wrapper():
    """Обёртка вокруг одной ветки — лишний уровень ни для чего."""
    assert group_by_shared_prefix(["Налоги - Жилплощадь", "Мебель"]) == {}


def test_an_existing_branch_becomes_the_parent_of_its_namesakes():
    """Под «Долги» уходят «Долги — Погашение» и «Долги — Возврат», а не под
    второй, только что придуманный «Долги»."""
    assignment = group_by_shared_prefix(["Долги", "Долги - Погашение", "Долги - Возврат"])
    assert assignment == {"Долги - Погашение": "Долги", "Долги - Возврат": "Долги"}
    assert "Долги" not in assignment


def test_a_short_list_is_left_flat():
    """Три строки мебели читаются и так; разбивать их — создавать работу."""
    assert group_by_meaning(["Мебель - Удобство", "Мебель - Хранение"]) == {}


def test_a_long_list_is_split_by_meaning():
    groups = group_by_meaning(
        [
            "Соки",
            "Газировки",
            "Компоты",
            "Кофе",
            "Овощные консервы",
            "Рыбные консервы",
            "Макароны",
            "Яйца",
            "Колбасы",
            "Хлеба",
        ]
    )
    assert groups["Соки"] == "Напитки"
    assert groups["Кофе"] == "Напитки"
    assert groups["Овощные консервы"] == "Консервы"
    # Одиночки группу не образуют: «Колбасы» единственное мясное, «Хлеба»
    # единственное хлебное — они остаются на своём месте.
    assert "Колбасы" not in groups
    assert "Хлеба" not in groups


def test_a_child_named_like_its_branch_does_not_become_its_own_parent():
    """В настоящей таблице есть ветка «Вода» с подкатегорией «Вода» — так
    помечали трату на ветку без уточнения. Раскладка по именам делала
    категорию родителем самой себе и вешала импорт бесконечной рекурсией."""
    plan = build_nesting({"Вода": ["Вода", "Вода минеральная", "Вода газированная"]})
    assert plan.branch_parent["Вода"] is None
    assert plan.leaf_group[("Вода", "Вода")] is None


def test_groups_do_not_merge_across_branches():
    """«Напитки» под продуктами и «Напитки» под бытовой химией — разные
    вещи, и склеивать их по имени нельзя."""
    plan = build_nesting(
        {
            "Продукты": ["Соки", "Газировки", "Компоты", "Кофе", "Макароны", "Яйца", "Соусы", "Масло"],
            "Бар": ["Соки", "Газировки", "Компоты", "Кофе", "Лёд", "Трубочки", "Бокалы", "Салфетки"],
        }
    )
    assert plan.new_levels["Продукты · Напитки"] == "Продукты"
    assert plan.new_levels["Бар · Напитки"] == "Бар"
    assert plan.leaf_group[("Продукты", "Соки")] == "Продукты · Напитки"
    assert plan.leaf_group[("Бар", "Соки")] == "Бар · Напитки"


def test_nothing_is_renamed():
    """Человек ищет свои категории по именам, которые сам придумал.
    «Улучшенное» имя означает, что он их больше не найдёт."""
    original = {
        "Электроника - Аксессуары": ["Наушники", "Флешки"],
        "Электроника - Комплектующие": ["Корпуса", "Охлаждение"],
    }
    plan = build_nesting(original)
    for parent, children in original.items():
        assert parent in plan.branch_parent
        for child in children:
            assert (parent, child) in plan.leaf_group


async def test_the_import_builds_the_deeper_tree(client: AsyncClient):
    """Раскладка применяется при переносе, а не отдельной кнопкой потом:
    разбирать 123 плоские строки руками никто не станет."""
    from tests.test_spreadsheet_import import csv_of, row

    content = csv_of(
        row(dds="Расходы", category="Электроника - Аксессуары", sub="Наушники", amount="1 000,00"),
        row(dds="Расходы", category="Электроника - Комплектующие", sub="Корпуса", amount="2 000,00"),
        row(dds="Расходы", category="Мебель", sub="Мебель - Хранение", amount="500,00"),
    )
    resp = await client.post(
        "/import/spreadsheet/apply",
        files={"transactions": ("transactions.csv", content.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text

    categories = {row_["name"]: row_ for row_ in (await client.get("/categories")).json()}
    # Появился уровень, которого в таблице не было.
    assert categories["Электроника"]["parent_id"] is None
    assert categories["Электроника - Аксессуары"]["parent_id"] == categories["Электроника"]["id"]
    assert categories["Наушники"]["parent_id"] == categories["Электроника - Аксессуары"]["id"]
    # Новый уровень — расходный, как и всё под ним: ветка не может быть
    # наполовину доходной.
    assert categories["Электроника"]["kind"] == "expense"
    # Мебель обёртки не получила: не с чем группировать.
    assert categories["Мебель"]["parent_id"] is None


async def test_amounts_still_reach_the_root_after_regrouping(client: AsyncClient):
    """Раскладка бесполезна, если суммы по ней не поднимаются: дерево,
    в котором наушники не попадают в электронику, хуже плоского списка."""
    from tests.test_spreadsheet_import import csv_of, row

    content = csv_of(
        row(dds="Расходы", category="Электроника - Аксессуары", sub="Наушники", amount="1 000,00", date="05.03.2026"),
        row(dds="Расходы", category="Электроника - Комплектующие", sub="Корпуса", amount="2 000,00", date="06.03.2026"),
    )
    resp = await client.post(
        "/import/spreadsheet/apply",
        files={"transactions": ("transactions.csv", content.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text

    categories = {row_["name"]: row_ for row_ in (await client.get("/categories")).json()}
    dashboard = (await client.get("/dashboard/summary?year=2026&month=3&range=month")).json()
    top = next(
        item for item in dashboard["spending_by_category"] if item["category_id"] == categories["Электроника"]["id"]
    )
    assert top["amount"] == "3000.00"
