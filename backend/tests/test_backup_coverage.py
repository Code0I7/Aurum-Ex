"""Полнота резервной копии.

Копия, молча теряющая половину данных, хуже её отсутствия: она обещает
безопасность, которой не даёт, и обнаруживается это ровно тогда, когда
восстанавливаться уже нужно.

Главный тест здесь — последний: он сверяет список таблиц в базе со списком
полей в файле копии и падает, когда в приложении появляется таблица, а в
копии нет. Проверять каждую таблицу отдельным тестом бессмысленно — через
полгода забудут дописать и тест, и поле.
"""
from decimal import Decimal

from httpx import AsyncClient

from app.db.base import Base
from app.schemas.backup import BackupPayload

# Таблицы, которых в копии нет намеренно. Сверяются с Base.metadata, поэтому
# alembic_version сюда не входит: этой таблицей управляет Alembic, и в модели
# приложения её нет вовсе.
NOT_BACKED_UP = {
    # Учётная запись и сессии: копия данных не должна переносить чужой
    # пароль и уж тем более открытые сессии на другую установку.
    "users",
    "sessions",
    # Служебное состояние опроса котировок — восстанавливается само при
    # первом обновлении цен.
    "crypto_sync_state",
    # Связующая таблица «операция — метка»: переносится внутри операций
    # (TransactionBackup.tag_ids).
    "transaction_tags",
}

# Как называется поле в BackupPayload, если оно не совпадает с именем
# таблицы.
FIELD_BY_TABLE = {
    "app_settings": "app_settings",
    "dashboard_widgets": "widgets",
}


async def test_a_full_install_survives_a_round_trip(client: AsyncClient, account_id, categories):
    """Заводим по одной записи в каждом новом разделе, выгружаем, стираем
    восстановлением и проверяем, что всё вернулось."""
    # Справочники.
    store = (await client.post("/stores", json={"name": "Магазин у дома"})).json()
    party = (await client.post("/counterparties", json={"name": "Брат"})).json()
    units = {row["name"]: row for row in (await client.get("/units")).json()}

    # Товар и чек с позицией.
    product = (
        await client.post(
            "/products", json={"name": "Хлеб чёрный", "unit_id": units["шт"]["id"]}
        )
    ).json()
    receipt = (
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "type": "expense",
                "amount": "45.00",
                "description": "Магазин",
                "date": "2026-03-01",
                "category_id": categories["Groceries"]["id"],
                "store_id": store["id"],
                "items": [
                    {
                        "product_id": product["id"],
                        "name": "Хлеб",
                        "quantity": "1",
                        "unit_id": units["шт"]["id"],
                        "amount": "45.00",
                    }
                ],
            },
        )
    ).json()
    assert len(receipt["items"]) == 1

    # Планирование и отработанное время.
    await client.post(
        "/plans",
        json={
            "kind": "monthly",
            "periods": [{"amount": "700.00", "valid_from": "2026-01-01"}],
            "category_id": categories["Housing & Utilities"]["id"],
        },
    )
    await client.put("/work-periods", json={"year": 2026, "month": 3, "hours": "160.00", "workdays": 20})

    # Кредит.
    credit = (
        await client.post("/accounts", json={"name": "Кредитка", "kind": "credit_card", "currency": "RUB"})
    ).json()
    await client.put(
        f"/accounts/{credit['id']}/credit-terms", json={"annual_rate_percent": "24.9", "credit_limit": "100000"}
    )

    # Инвестиции.
    portfolio = (await client.post("/investments/portfolios", json={"name": "Долгосрок"})).json()
    holding = (
        await client.post(
            "/investments/holdings",
            json={"portfolio_id": portfolio["id"], "name": "ACME", "kind": "stock", "currency": "RUB"},
        )
    ).json()
    await client.post(
        f"/investments/holdings/{holding['id']}/trades",
        json={"side": "buy", "quantity": "10", "price_per_unit": "100", "fee": "0", "trade_date": "2026-01-10"},
    )

    # Расчёт с человеком — чтобы контрагент оказался использован.
    await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "external_out",
            "amount": "5000.00",
            "description": "В долг",
            "date": "2026-03-02",
            "counterparty_id": party["id"],
            "settlement_kind": "loan_out",
            "category_id": None,
        },
    )

    backup = (await client.get("/backup/export")).json()

    # Всё перечисленное обязано лежать в файле, а не потеряться молча.
    assert len(backup["stores"]) == 1
    assert len(backup["counterparties"]) == 1
    assert len(backup["products"]) == 1
    assert len(backup["transaction_items"]) == 1
    assert len(backup["plans"]) == 1
    assert len(backup["work_periods"]) == 1
    assert len(backup["credit_terms"]) == 1
    assert len(backup["investment_portfolios"]) == 1
    assert len(backup["investment_holdings"]) == 1
    assert len(backup["investment_trades"]) == 1
    assert len(backup["units"]) > 0
    assert len(backup["currencies"]) > 0

    # Восстановление стирает всё и раскладывает заново.
    resp = await client.post("/backup/import", json=backup)
    assert resp.status_code == 200, resp.text

    assert len((await client.get("/products")).json()) == 1
    assert len((await client.get("/plans")).json()) == 1
    assert len((await client.get("/work-periods")).json()) == 1
    assert len((await client.get("/credits")).json()) == 1
    assert len((await client.get("/investments/holdings")).json()) == 1

    # Позиция чека вернулась вместе с операцией.
    listing = (await client.get("/transactions")).json()
    restored = next(row for row in listing["items"] if row["description"] == "Магазин")
    assert restored["items"][0]["name"] == "Хлеб"

    # И расчёт с человеком тоже.
    settlements = (await client.get("/settlements")).json()
    assert Decimal(settlements[0]["owed_to_me"]) == Decimal("5000")

    # Инвестиции пересчитались из восстановленного журнала сделок.
    holdings = (await client.get("/investments/holdings")).json()
    assert Decimal(holdings[0]["cost_basis"]) == Decimal("1000")


def test_every_table_is_either_backed_up_or_deliberately_excluded():
    """Страховка от забывчивости: таблица, появившаяся в приложении, ломает
    этот тест, пока её не добавят в копию или не внесут в список исключений
    с объяснением.

    Без такой проверки пробел обнаруживается только при восстановлении — то
    есть в худший возможный момент.
    """
    tables = {table.name for table in Base.metadata.sorted_tables}
    fields = set(BackupPayload.model_fields)

    missing = set()
    for table in sorted(tables - NOT_BACKED_UP):
        field = FIELD_BY_TABLE.get(table, table)
        if field not in fields:
            missing.add(table)

    assert not missing, f"таблицы есть в базе, но не попадают в резервную копию: {sorted(missing)}"

    # И наоборот: список исключений не должен ссылаться на то, чего уже нет.
    stale = NOT_BACKED_UP - tables
    assert not stale, f"в списке исключений таблицы, которых больше нет: {sorted(stale)}"


async def test_every_table_keeps_its_rows_through_a_restore(client: AsyncClient, account_id, categories):
    """Сверка по всем таблицам разом: сколько строк было до выгрузки,
    столько же должно остаться после восстановления.

    Проверять поштучно бессмысленно — забудут дописать проверку ровно для той
    таблицы, которую забыли положить в копию. Здесь пересчитываются все, и
    новая таблица попадает под проверку сама.
    """
    # Заводим по строке в справочниках, до которых поимённые проверки не
    # доходят: банк, метка, курс валюты, участник, виджет дашборда.
    bank = (await client.post("/banks", json={"name": "Первый банк"})).json()
    await client.patch(f"/accounts/{account_id}", json={"bank_id": bank["id"]})
    await client.post("/participants", json={"name": "Иван", "kind": "person"})
    await client.post("/stores", json={"name": "Магазин у дома"})
    await client.post("/counterparties", json={"name": "Брат"})

    tag = (await client.post("/tags", json={"name": "важное", "color": "#2a78d6"})).json()
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "100.00",
            "description": "Покупка",
            "date": "2026-03-01",
            "category_id": categories["Groceries"]["id"],
            "tag_ids": [tag["id"]],
        },
    )
    assert resp.status_code == 201, resp.text

    before = await _table_counts(client)
    backup = (await client.get("/backup/export")).json()
    assert (await client.post("/backup/import", json=backup)).status_code == 200

    after = await _table_counts(client)
    lost = {name: (before[name], after[name]) for name in before if before[name] != after[name]}
    assert not lost, f"после восстановления строки не сошлись: {lost}"


async def _table_counts(client: AsyncClient) -> dict[str, int]:
    """Сколько строк в каждой таблице, кроме намеренно не копируемых.

    Считается через ту же сессию, что и запросы теста, — иначе пришлось бы
    заводить второе подключение и следить, чтобы оно видело те же данные.
    """
    from sqlalchemy import func, select

    from app.api.deps import get_session
    from app.main import app

    override = app.dependency_overrides[get_session]
    counts: dict[str, int] = {}
    async for session in override():
        for table in Base.metadata.sorted_tables:
            if table.name in NOT_BACKED_UP:
                continue
            counts[table.name] = int(
                (await session.execute(select(func.count()).select_from(table))).scalar_one()
            )
        break
    return counts


# Колонки, которые копия не переносит намеренно. Всё остальное обязано в
# ней быть — иначе восстановление молча возвращает значение по умолчанию.
COLUMNS_NOT_BACKED_UP = {
    # Служебные отметки времени: они относятся к строке в этой базе, а не
    # к данным, и после восстановления должны проставиться заново.
    "created_at",
    "updated_at",
    # Единственная строка настроек всегда id=1.
    ("app_settings", "id"),
}


def test_every_column_is_in_the_backup():
    """Проверка от настоящей потери. Настройки вида — период обзора, размер
    страницы, склейка повторов, разделители дней — добавились миграцией
    0002, а в схему копии их дописать забыли. Копия снималась без ошибки,
    восстанавливалась без ошибки, и настройки молча возвращались к
    умолчанию; заметить это можно было бы только по тому, что список
    операций снова открывается на двадцати строках.

    Проверка таблиц такого не ловит: таблица-то в копии есть. Поэтому
    сверяются колонки.
    """
    from app.db.base import Base
    from app.schemas import backup as backup_schemas

    # Схема копии для таблицы ищется по имени класса: FooBarBackup для
    # foo_bars. Пары, где это правило не работает, перечислены явно.
    special = {"app_settings": "AppSettingsBackup", "dashboard_widgets": "WidgetBackup"}

    missing: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name in NOT_BACKED_UP:
            continue
        class_name = special.get(table.name)
        if class_name is None:
            singular = table.name[:-1] if table.name.endswith("s") else table.name
            class_name = "".join(part.title() for part in singular.split("_")) + "Backup"
        schema = getattr(backup_schemas, class_name, None)
        if schema is None:
            # Схема названа иначе — не повод молчать, но и не эта проверка.
            continue
        fields = set(schema.model_fields)
        for column in table.columns:
            if column.name in COLUMNS_NOT_BACKED_UP:
                continue
            if (table.name, column.name) in COLUMNS_NOT_BACKED_UP:
                continue
            if column.name not in fields:
                missing.append(f"{table.name}.{column.name} -> {class_name}")

    assert not missing, "Колонки не попадают в резервную копию: " + ", ".join(sorted(missing))
