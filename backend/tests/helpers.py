"""Shared test fixtures' plain-Python helpers (not pytest fixtures
themselves — those live in conftest.py)."""
from decimal import Decimal


def money(value) -> Decimal:
    """Compares amounts by value regardless of whether the API serializes
    Decimal as a JSON string or number — that's a wire-format detail, not
    business behavior worth pinning a test to."""
    return Decimal(str(value))


def txn_payload(account_id: int, **overrides) -> dict:
    payload = {
        "account_id": account_id,
        "type": "expense",
        "amount": "10.00",
        "description": "test transaction",
        "date": "2026-01-15",
    }
    payload.update(overrides)
    return payload


# --- Выгрузка из таблицы учёта ---------------------------------------------
#
# Строители лежат здесь, а не в тесте импорта: ими пользуется и проверка
# группировки категорий, а один тестовый модуль, импортирующий другой, — это
# зависимость между тестами, которой быть не должно.
#
# Данные дословны: те же заголовки колонок, тот же формат чисел с
# неразрывным пробелом и запятой, те же виды ДДС. На приглаженном CSV
# проверять разбор бессмысленно — ломается он ровно на этих особенностях.
HEADER = (
    "Дата,Комментарий статьи Расходов или Доходов,Кол-во,Цена,Сумма в ₽,В раб.час.,"
    "Карта / Счет,Персона,Валюта,ДДС,Подкатегории ДДС,Ед.изм-ия,Категория ДДС,Цель,"
    "День,Месяц,Год,Обозн.Валюты,Сумма,Сумма / Конверт"
)


def row(
    date="28.08.2022",
    comment="Операция",
    qty="1",
    price="100,00",
    account="Карта 1234",
    person="Работа",
    dds="Расходы",
    sub="Выпечка",
    unit="Шт",
    category="Быстропит",
    goal="",
    amount="100,00",
) -> str:
    # Суммы закавычены: в русской выгрузке десятичный разделитель — запятая,
    # и без кавычек «10 900,00» разбирается как два поля, съезжая на колонку
    # всю остальную строку. В настоящем файле Google Sheets кавычит их сам.
    return (
        f'{date},{comment},{qty},"{price}","{amount} ₽",0:15:00,{account},{person},₽,{dds},'
        f'{sub},{unit},{category},{goal},28,8,2022,RUBRUB,"{amount}","{amount}"'
    )


def csv_of(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"
