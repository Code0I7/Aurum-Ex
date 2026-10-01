"""Движок FIFO на бумажных примерах.

Синхронные тесты без базы: если цифра в отчёте вызывает спор, спор решается
здесь. Пример из документации к модели вынесен первым — он и есть причина,
по которой средневзвешенную заменили.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.fifo import Position, buy, replay, sell


@dataclass
class FakeTrade:
    side: str
    quantity: Decimal
    price_per_unit: Decimal
    fee: Decimal = Decimal("0")
    trade_date: date | None = None


def d(value: str) -> Decimal:
    return Decimal(value)


def test_fifo_and_weighted_average_disagree_by_an_order_of_magnitude():
    """Куплено 1 шт по 500 и 5 шт по 100, продано 2 шт по 150.

    FIFO списывает самые старые: 500 + 100 = 600 против выручки 300 —
    убыток 300. Средневзвешенная дала бы 166,67 за штуку и убыток 33.
    """
    position = Position()
    buy(position, d("1"), d("500"), d("0"))
    buy(position, d("5"), d("100"), d("0"))
    sell(position, d("2"), d("150"), d("0"))

    assert position.realised == d("-300")
    assert position.quantity == d("4")
    # Осталось четыре штуки из второй партии, по 100 каждая.
    assert position.cost_basis == d("400")
    assert position.average_cost == d("100")


def test_a_fee_raises_the_cost_of_a_purchase():
    """Комиссия входит в стоимость: иначе доходность завышена ровно на то,
    что заплачено брокеру."""
    position = Position()
    buy(position, d("10"), d("100"), d("50"))

    assert position.cost_basis == d("1050")
    assert position.average_cost == d("105")
    assert position.invested == d("1050")


def test_a_fee_lowers_the_proceeds_of_a_sale():
    """Продать на 300 и отдать 10 брокеру значит получить 290."""
    position = Position()
    buy(position, d("10"), d("100"), d("0"))
    disposal = sell(position, d("2"), d("150"), d("10"))

    assert disposal.proceeds == d("290")
    assert disposal.cost == d("200")
    assert disposal.realised == d("90")


def test_lots_are_consumed_oldest_first_across_several_purchases():
    position = Position()
    buy(position, d("3"), d("10"), d("0"), date(2022, 1, 1))
    buy(position, d("3"), d("20"), d("0"), date(2023, 1, 1))
    buy(position, d("3"), d("30"), d("0"), date(2024, 1, 1))

    # Продаём пять: три по 10 и две по 20 = 70.
    disposal = sell(position, d("5"), d("50"), d("0"))
    assert disposal.cost == d("70")
    assert disposal.proceeds == d("250")
    assert disposal.realised == d("180")

    # Отчёт помнит, из чего списали: «продали то, что купили в 2022-м».
    assert [(qty, cost, when) for qty, cost, when in disposal.lots] == [
        (d("3"), d("10"), date(2022, 1, 1)),
        (d("2"), d("20"), date(2023, 1, 1)),
    ]
    # Осталось: одна по 20 и три по 30.
    assert position.quantity == d("4")
    assert position.cost_basis == d("110")


def test_selling_everything_empties_the_position():
    position = Position()
    buy(position, d("5"), d("100"), d("0"))
    sell(position, d("5"), d("120"), d("0"))

    assert position.quantity == d("0")
    assert position.cost_basis == d("0")
    # У пустой позиции нет цены владения.
    assert position.average_cost is None
    assert position.realised == d("100")


def test_selling_more_than_held_is_reported_not_hidden():
    """Не ошибка расчёта, а ошибка в данных: пропущенная покупка или
    неверная дата. Прятать её нельзя."""
    position = Position()
    buy(position, d("2"), d("100"), d("0"))
    sell(position, d("5"), d("150"), d("0"))

    assert position.oversold == d("3")
    assert position.quantity == d("0")
    # Стоимость лишнего считается нулевой: придумывать цену, которой не
    # было, хуже, чем показать расхождение.
    assert position.realised == d("550")


def test_buying_again_after_selling_out_starts_a_fresh_lot():
    """Продажа всего не должна оставлять хвостов, из-за которых следующая
    покупка считалась бы по старой цене."""
    position = Position()
    buy(position, d("5"), d("100"), d("0"))
    sell(position, d("5"), d("120"), d("0"))
    buy(position, d("2"), d("300"), d("0"))

    assert position.quantity == d("2")
    assert position.average_cost == d("300")
    # Зафиксированная прибыль от первой сделки никуда не делась.
    assert position.realised == d("100")


def test_fractional_quantities_survive_the_replay():
    """Крипта дробится до восьми знаков — округление здесь недопустимо."""
    position = Position()
    buy(position, d("0.00000001"), d("5000000"), d("0"))
    buy(position, d("0.5"), d("4000000"), d("0"))

    assert position.quantity == d("0.50000001")
    assert position.cost_basis == d("2000000.05")


def test_replay_walks_the_log_in_the_order_given():
    """Порядок задаёт вызывающая сторона: тай-брейк внутри дня — её дело."""
    position = replay(
        [
            FakeTrade("buy", d("1"), d("500"), trade_date=date(2026, 1, 1)),
            FakeTrade("buy", d("5"), d("100"), trade_date=date(2026, 1, 1)),
            FakeTrade("sell", d("2"), d("150"), trade_date=date(2026, 2, 1)),
        ]
    )
    assert position.realised == d("-300")

    # Тот же день, обратный порядок — другой результат, и это правильно:
    # FIFO списывает то, что было куплено раньше по журналу.
    reversed_position = replay(
        [
            FakeTrade("buy", d("5"), d("100"), trade_date=date(2026, 1, 1)),
            FakeTrade("buy", d("1"), d("500"), trade_date=date(2026, 1, 1)),
            FakeTrade("sell", d("2"), d("150"), trade_date=date(2026, 2, 1)),
        ]
    )
    assert reversed_position.realised == d("100")


def test_invested_and_cost_basis_are_different_numbers():
    """cost_basis — во сколько обошлось то, что ещё на руках; invested —
    сколько всего денег вложено покупками."""
    position = Position()
    buy(position, d("10"), d("100"), d("0"))
    sell(position, d("4"), d("200"), d("0"))

    assert position.invested == d("1000")
    assert position.cost_basis == d("600")
    assert position.proceeds == d("800")
