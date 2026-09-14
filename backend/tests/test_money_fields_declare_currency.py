"""Величина в своей валюте обязана эту валюту отдавать.

Проверка формы ответов, а не поведения, и существует она из-за ошибки,
которую мы ловили по одному месту целый день: сумма в евро уезжала наружу
голым числом, интерфейс печатал её с подписью валюты установки, и сто евро
выглядели как сто рублей. Арифметика была верной. Врала подпись.

Величин всего два вида:

* **событие** — что произошло в конкретный день: операция, позиция чека,
  передача денег человеку. Переводится один раз, курсом своего дня, и
  замерзает. Итог, сложенный из событий, всегда в валюте установки, и
  отдельного поля валюты ему не нужно — она одна на всё приложение;
* **состояние** — что есть сейчас: остаток счёта, оценка имущества, цена
  бумаги, долг по карте. Не переводится никогда и живёт в своей валюте.
  Вот его-то и нельзя отдавать, не сказав, в чём оно.

Здесь перечислены модели второго вида. Каждая обязана нести поле валюты
рядом со своими суммами — и тест упадёт, если поле уберут или переименуют.

Почему список, а не сплошная проверка всех моделей с суммами: сплошная
даёт шесть десятков записей, из которых пять десятков — «да, это итог в
валюте установки». Реестр такого размера никто не читает, и он превращается
в шум, сквозь который настоящая ошибка проходит незамеченной. Список же
короткий, и каждая строка в нём — сущность с собственной валютой, которую
можно назвать вслух.
"""
import importlib
import pkgutil
from decimal import Decimal
from typing import get_args, get_origin

import pytest
from pydantic import BaseModel

import app.schemas

# Чем модель может сказать, в какой валюте её суммы.
CURRENCY_FIELDS = {"currency", "account_currency", "transfer_currency"}


# Модели, суммы которых — в собственной валюте сущности, а не в валюте
# установки. Рядом сказано, чья это валюта: если однажды окажется, что
# сказать нечего, значит, модель тут лишняя.
OWN_CURRENCY_MODELS = {
    # Счёт: остаток — состояние, и сто евро на евровой карте это сто евро.
    "AccountRead": "валюта счёта",
    "AccountWithBalance": "валюта счёта",
    "AccountBalanceItem": "валюта счёта (обзор)",
    "CreditTermsRead": "валюта карты, по которой долг",
    # Операция: сумма записана в той валюте, в которой прошла.
    "TransactionRead": "валюта операции",
    "SimilarTransaction": "валюта операции",
    "TransferMatchSide": "валюта операции (пара похожих на один перевод)",
    # Имущество и вложения: оценка и цена — состояние.
    "AssetRead": "валюта оценки имущества",
    "HoldingRead": "валюта бумаги",
    "HoldingDetail": "валюта бумаги",
}

# Поля, похожие на деньги по имени, но деньгами не являющиеся.
NOT_MONEY = {"value_kind", "price_unit", "price_kind", "last_price_kind"}

MONEY_WORDS = (
    "amount",
    "balance",
    "value",
    "price",
    "cost",
    "debt",
    "payment",
    "limit",
    "available",
    "reserved",
    "opening",
)


def _mentions_decimal(annotation: object) -> bool:
    """Decimal где угодно внутри аннотации — в том числе в `Decimal | None`
    и в `list[Decimal]`."""
    if annotation is Decimal:
        return True
    if get_origin(annotation) is None:
        return False
    return any(_mentions_decimal(arg) for arg in get_args(annotation))


def _money_fields(model: type[BaseModel]) -> list[str]:
    return [
        name
        for name, field in model.model_fields.items()
        if name not in NOT_MONEY
        and name not in CURRENCY_FIELDS
        and any(word in name for word in MONEY_WORDS)
        and _mentions_decimal(field.annotation)
        # Приведённая сумма говорит о своей валюте собственным именем.
        and not name.endswith("_base")
    ]


def _all_models() -> dict[str, type[BaseModel]]:
    models: dict[str, type[BaseModel]] = {}
    for module in pkgutil.iter_modules(app.schemas.__path__):
        imported = importlib.import_module(f"app.schemas.{module.name}")
        for value in vars(imported).values():
            if isinstance(value, type) and issubclass(value, BaseModel) and value is not BaseModel:
                models[value.__name__] = value
    return models


@pytest.mark.parametrize("name", sorted(OWN_CURRENCY_MODELS), ids=str)
def test_a_model_in_its_own_currency_says_which_one(name: str):
    models = _all_models()
    assert name in models, f"модели {name} больше нет — уберите её из списка"
    model = models[name]

    assert CURRENCY_FIELDS & set(model.model_fields), (
        f"{name} несёт суммы {_money_fields(model)} в собственной валюте "
        f"({OWN_CURRENCY_MODELS[name]}), но поля валюты у неё нет.\n"
        f"Без него интерфейсу остаётся подписать их валютой установки — "
        f"и сто евро станут ста рублями."
    )


@pytest.mark.parametrize("name", sorted(OWN_CURRENCY_MODELS), ids=str)
def test_a_model_in_the_list_actually_carries_money(name: str):
    """Модель без сумм в списке не нужна: список должен оставаться списком
    того, за чем правда надо следить."""
    model = _all_models()[name]

    assert _money_fields(model), f"{name} больше не несёт сумм — уберите её из списка"
