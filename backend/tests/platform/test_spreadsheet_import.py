"""Перенос истории из таблицы учёта.

Данные в тестах — сокращённая, но дословная копия настоящей выгрузки:
те же заголовки колонок, тот же формат чисел с неразрывным пробелом и
запятой, те же виды ДДС по-русски. Проверять разбор на приглаженном CSV
бессмысленно — ломается он ровно на этих особенностях.
"""
import pytest
from httpx import AsyncClient

from decimal import Decimal

from app.services.spreadsheet_import_service import build_plan, parse_amount, parse_date

from tests.helpers import csv_of, row

# Глобальной метки asyncio здесь нет намеренно: pytest.ini включает
# asyncio_mode = auto, и async-тесты подхватываются сами, а синхронные
# проверки разбора от такой метки только ломаются.

# --- Разбор чисел и дат ---


def test_amount_parses_russian_formatting():
    """Неразрывный пробел как разделитель тысяч и запятая как десятичный
    знак — то, что реально лежит в выгрузке."""
    assert parse_amount("12\xa0700,00") == 12700
    assert parse_amount("5 210,40 ₽") == Decimal("5210.40")
    assert parse_amount("100,00") == 100


def test_amount_treats_a_dash_as_no_value():
    """Прочерк — это обнулённая запись-памятка, а не ошибка разбора."""
    assert parse_amount("-") is None
    assert parse_amount("") is None
    assert parse_amount(None) is None


def test_date_parses_day_first():
    assert parse_date("26.08.2024").isoformat() == "2024-08-26"
    assert parse_date("не дата") is None


# --- Сборка плана ---


def test_transfer_halves_are_matched_back_into_one_record():
    """«Списание» и «Зачисление» — две половины одного перевода, и склеить
    их обратно можно только по дате и сумме: других связей в таблице нет."""
    plan = build_plan(
        csv_of(
            row(dds="Списание", account="Карта 1234", amount="10 900,00", sub="", category=""),
            row(dds="Зачисление", account="Наличные", amount="10 900,00", sub="", category=""),
        )
    )
    assert len(plan.transfers) == 1
    outgoing, incoming = plan.transfers[0]
    assert outgoing.account == "Карта 1234"
    assert incoming.account == "Наличные"
    assert not plan.issues


def test_an_unmatched_transfer_half_is_reported_not_dropped():
    """Потерять перевод молча — худшее, что может сделать импорт."""
    plan = build_plan(csv_of(row(dds="Списание", amount="500,00", sub="", category="")))
    assert not plan.transfers
    assert [issue.reason for issue in plan.issues] == ["unmatched_transfer_out"]


def test_opening_deposit_becomes_an_account_balance_not_income():
    """5 210,40 ₽ лежали на карте до начала учёта. Проведённые доходом, они
    завысили заработок 2022 года на 24 %."""
    plan = build_plan(
        csv_of(
            row(
                comment="Стартовое внесение",
                dds="Доходы",
                amount="5 210,40",
                sub="Работа - Премия",
                category="Работа",
            )
        )
    )
    assert plan.incomes == []
    assert len(plan.openings) == 1
    assert plan.accounts["Карта 1234"] == Decimal("5210.40")


def test_zeroed_quantity_marks_a_row_as_not_counted():
    """Возвращённый товар: покупка была, помнить о ней нужно, а в суммы она
    входить не должна. В исходных данных так помечены 8 записей."""
    plan = build_plan(csv_of(row(qty="0", amount="-", price="9 000,00", comment="Брату на телефон")))
    assert len(plan.expenses) == 1
    assert plan.expenses[0].is_excluded is True
    # Сумма восстановлена из цены — иначе о какой покупке речь, непонятно.
    assert plan.expenses[0].amount == 9000


def test_reserves_and_releases_are_goal_moves_not_corrections():
    """«Присвоить» и «Изъять» — конверты на фиктивном счёте, а не правки."""
    plan = build_plan(
        csv_of(
            row(dds="Присвоить", account="Копилка", amount="4 500,00", goal="Новый телефон", sub="", category=""),
            row(dds="Изъять", account="Копилка", amount="4 500,00", goal="Новый телефон", sub="", category=""),
        )
    )
    assert len(plan.reserves) == 1
    assert len(plan.releases) == 1
    assert plan.goals == {"Новый телефон"}


def test_categories_keep_their_two_level_shape():
    plan = build_plan(csv_of(row(category="Продукты", sub="Хлеба")))
    assert plan.categories["Продукты"] == {"Хлеба"}


def test_blank_trailing_rows_are_skipped_silently():
    """В выгрузке пять пустых строк-хвостов; ошибкой они не являются."""
    plan = build_plan(csv_of(row(), ",,,,,,,,,,,,,,,,,,,"))
    assert plan.total_rows == 1
    assert not plan.issues


# --- Эндпоинты ---


async def test_preview_reports_what_would_happen_without_writing(client: AsyncClient):
    content = csv_of(
        row(dds="Доходы", amount="500,00", sub="Работа - Зарплата", category="Работа"),
        row(dds="Расходы", amount="150,00"),
    )
    resp = await client.post(
        "/import/spreadsheet/preview",
        files={"transactions": ("transactions.csv", content.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200
    plan = resp.json()
    assert plan["incomes"] == 1
    assert plan["expenses"] == 1
    assert plan["can_apply"] is True

    # Предпросмотр ничего не пишет.
    assert (await client.get("/transactions")).json()["total"] == 0


async def test_apply_imports_the_history(client: AsyncClient):
    content = csv_of(
        row(comment="Стартовое внесение", dds="Доходы", amount="1 000,00", sub="Работа - Зарплата", category="Работа"),
        row(dds="Доходы", amount="500,00", sub="Работа - Зарплата", category="Работа"),
        row(dds="Расходы", amount="150,00"),
        row(dds="Списание", account="Карта 1234", amount="200,00", sub="", category=""),
        row(dds="Зачисление", account="Наличные", amount="200,00", sub="", category=""),
    )
    resp = await client.post(
        "/import/spreadsheet/apply",
        files={"transactions": ("transactions.csv", content.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["transactions"] == 2  # доход и расход; стартовое стало остатком
    assert result["transfers"] == 1

    listing = (await client.get("/transactions")).json()
    assert listing["total"] == 3  # доход, расход и один перевод

    accounts = {account["name"]: account for account in (await client.get("/accounts")).json()}
    assert accounts["Карта 1234"]["opening_balance"] == "1000.00"
    # 1000 начального остатка + 500 дохода − 150 расхода − 200 перевода.
    assert accounts["Карта 1234"]["balance"] == "1150.00"
    assert accounts["Наличные"]["balance"] == "200.00"


async def test_apply_is_refused_on_a_non_empty_database(client: AsyncClient, account_id, categories):
    """Второй импорт удвоил бы историю, а разобрать потом, какая из двух
    одинаковых поездок лишняя, невозможно."""
    await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "10.00",
            "description": "Уже есть",
            "date": "2024-01-01",
            "category_id": categories["Groceries"]["id"],
        },
    )

    resp = await client.post(
        "/import/spreadsheet/apply",
        files={"transactions": ("t.csv", csv_of(row()).encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 409


# --- Кредитные счета ---


def test_credit_accounts_are_found_by_interest_not_by_name():
    """Название счёта — ненадёжный признак. «Маркет Кредит» о себе говорит,
    «Маркет 2222» молчит, а проценты начисляются на оба."""
    plan = build_plan(
        csv_of(
            row(account="Маркет 2222", dds="Расходы", category="Долги - Погашение",
                sub="Проценты по кредитам", amount="1 200,00"),
            row(account="Банк 1111", dds="Расходы", category="Долги - Погашение",
                sub="Погашение кредитов", amount="5 000,00"),
            row(account="Банк 1111", dds="Доходы", category="Иван", sub="Иван - Зарплата",
                amount="50 000,00"),
        )
    )
    assert plan.credit_accounts == {"Маркет 2222"}


def test_repayment_does_not_mark_the_paying_account_as_credit():
    """Погашение списывается с обычного счёта, с которого платят. Считать
    кредитным его — значит перепутать должника с кредитом."""
    plan = build_plan(
        csv_of(
            row(account="Банк 1111", dds="Расходы", category="Долги - Погашение",
                sub="Погашение кредитов", amount="5 000,00"),
        )
    )
    assert plan.credit_accounts == set()


async def test_an_account_with_interest_is_flagged_but_not_reclassified(client: AsyncClient):
    """Правило «на счёт начисляли проценты → он кредитный» ошибается: с
    дебетовой карты тоже можно заплатить проценты по рассрочке. Поэтому
    находка показывается в отчёте, а вид счёта не
    меняется — кто из них кредитный, знает владелец."""
    payload = csv_of(
        row(account="Маркет 2222", dds="Расходы", category="Долги - Погашение",
            sub="Проценты по кредитам", amount="1 200,00"),
        row(account="Наличные", dds="Расходы", category="Быстропит", sub="Выпечка", amount="100,00"),
    )
    resp = await client.post(
        "/import/spreadsheet/apply",
        files={"transactions": ("transactions.csv", payload.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text

    accounts = {item["name"]: item for item in (await client.get("/accounts")).json()}
    # Имя ничего про кредит не говорит — счёт остаётся обычным.
    assert accounts["Маркет 2222"]["nature"] == "asset"
    assert accounts["Наличные"]["nature"] == "asset"

    # А в отчёте перед импортом он назван: человеку есть что проверить.
    preview = await client.post(
        "/import/spreadsheet/preview",
        files={"transactions": ("transactions.csv", payload.encode("utf-8"), "text/csv")},
    )
    assert "Маркет 2222" in preview.json()["credit_accounts"]


async def test_one_misfiled_row_does_not_flip_a_whole_category(client: AsyncClient):
    """В настоящей таблице у «Прочих расходов» 179 расходных строк и одна
    доходная — человек однажды промахнулся видом операции. Правило «есть
    хоть один доход → категория доходная» переносило всю ветку не на ту
    сторону: расход на восемьдесят тысяч оказывался доходом."""
    content = csv_of(
        *[
            row(dds="Расходы", category="Прочие расходы", sub="Прочие расходы - Переводы", amount="300,00")
            for _ in range(5)
        ],
        row(dds="Доходы", category="Прочие расходы", sub="Прочие расходы - Переводы", amount="200,00"),
    )
    resp = await client.post(
        "/import/spreadsheet/apply",
        files={"transactions": ("transactions.csv", content.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text

    categories = {c["name"]: c for c in (await client.get("/categories")).json()}
    assert categories["Прочие расходы"]["kind"] == "expense"
    # Подкатегория наследует вид родителя: одна ветка не может быть наполовину
    # доходной.
    assert categories["Прочие расходы - Переводы"]["kind"] == "expense"


def test_a_row_without_a_comment_stays_without_a_description():
    """Пусто остаётся пустым.

    Заглушка «Без описания» стояла в импорте, пока описание было
    обязательным полем: у половины строк исходной таблицы комментария нет,
    и иначе импорт не проходил. Поле стало необязательным в beta.4, а
    заглушка осталась — и превратилась в две с половиной сотни строк
    текста, который ничего не сообщает, зато попадает и в поиск, и в
    проверку повторов.
    """
    plan = build_plan(csv_of(row(comment="")))
    assert len(plan.expenses) == 1
    assert plan.expenses[0].description is None
