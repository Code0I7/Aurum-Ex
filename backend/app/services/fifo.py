"""Списание партий по FIFO.

Чистая арифметика, без базы и без веб-слоя: движок разбирается на бумажных
примерах, и любой спор о цифре решается здесь, а не в отчёте.

**Почему FIFO, а не средневзвешенная.** Два метода расходятся на порядок на
одной и той же сделке:

    Куплено:  1 шт по 500 ₽, затем 5 шт по 100 ₽  →  6 шт за 1 000 ₽
    Продано:  2 шт по 150 ₽                       →  выручка 300 ₽

    FIFO:     списываются самые старые (500 + 100 = 600)  →  убыток 300 ₽
    Средняя:  1000 / 6 = 166,67 за штуку (333 ₽)          →  убыток 33 ₽

FIFO — то, чем считает отчёт брокера и чего требует налоговая, поэтому
цифры здесь сходятся с цифрами в приложении брокера, а не тихо им
противоречат. Один метод на всё приложение заодно предотвращает худшее: две
соседние вкладки, расходящиеся в оценке одинаковых операций.

**Комиссия.** Входит в стоимость покупки и уменьшает выручку от продажи.
Иначе доходность оказывается завышенной ровно на сумму, которую человек
заплатил брокеру.
"""
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Lot:
    """Открытая партия: сколько осталось и по какой цене куплено.

    `cost_per_unit` включает долю комиссии покупки — считать её отдельно
    значило бы каждый раз вспоминать, учтена она уже или нет.
    """

    quantity: Decimal
    cost_per_unit: Decimal
    # Дата покупки — нужна для отчёта «что именно списалось», а не для
    # арифметики: порядок задаёт сама очередь.
    acquired_on: object = None

    @property
    def cost(self) -> Decimal:
        return self.quantity * self.cost_per_unit


@dataclass
class Disposal:
    """Одна продажа после разнесения по партиям."""

    quantity: Decimal
    proceeds: Decimal
    cost: Decimal
    # Партии, из которых списали, — чтобы отчёт мог показать «продали то,
    # что купили в мае 2022».
    lots: list[tuple[Decimal, Decimal, object]] = field(default_factory=list)

    @property
    def realised(self) -> Decimal:
        """Реализованная прибыль: за сколько продали минус во сколько
        обошлось то, что продали."""
        return self.proceeds - self.cost


@dataclass
class Position:
    """Итог прогона: что осталось на руках и что уже зафиксировано."""

    quantity: Decimal = Decimal("0")
    cost_basis: Decimal = Decimal("0")
    realised: Decimal = Decimal("0")
    proceeds: Decimal = Decimal("0")
    # Сколько денег всего вложено покупками, с комиссиями. Не то же, что
    # cost_basis: часть вложенного уже продана.
    invested: Decimal = Decimal("0")
    lots: list[Lot] = field(default_factory=list)
    disposals: list[Disposal] = field(default_factory=list)
    # Продажи, которым не хватило партий. Это не ошибка расчёта, а ошибка в
    # данных: пропущенная покупка, неверная дата. Прятать её нельзя.
    oversold: Decimal = Decimal("0")

    @property
    def average_cost(self) -> Decimal | None:
        """Средняя цена того, что осталось. None при нулевом остатке —
        у пустой позиции нет цены владения."""
        if self.quantity <= 0:
            return None
        return self.cost_basis / self.quantity


def buy(position: Position, quantity: Decimal, price_per_unit: Decimal, fee: Decimal, on_date=None) -> None:
    """Открывает партию. Комиссия размазывается по единицам: партия должна
    знать свою полную стоимость, иначе при продаже придётся вспоминать,
    сколько сверху было заплачено брокеру."""
    if quantity <= 0:
        return
    total_cost = quantity * price_per_unit + fee
    position.lots.append(
        Lot(quantity=quantity, cost_per_unit=total_cost / quantity, acquired_on=on_date)
    )
    position.quantity += quantity
    position.cost_basis += total_cost
    position.invested += total_cost


def sell(position: Position, quantity: Decimal, price_per_unit: Decimal, fee: Decimal) -> Disposal:
    """Списывает самые старые партии, пока не покроет проданное.

    Выручка уменьшается на комиссию: продать на 300 ₽ и отдать 10 ₽ брокеру
    значит получить 290 ₽, и прибыль надо считать от этой суммы.
    """
    proceeds = quantity * price_per_unit - fee
    disposal = Disposal(quantity=quantity, proceeds=proceeds, cost=Decimal("0"))

    remaining = quantity
    while remaining > 0 and position.lots:
        lot = position.lots[0]
        take = min(remaining, lot.quantity)
        cost = take * lot.cost_per_unit
        disposal.cost += cost
        disposal.lots.append((take, lot.cost_per_unit, lot.acquired_on))
        lot.quantity -= take
        remaining -= take
        position.quantity -= take
        position.cost_basis -= cost
        if lot.quantity <= 0:
            position.lots.pop(0)

    if remaining > 0:
        # Партий не хватило. Считаем стоимость проданного сверх остатка
        # нулевой — иначе пришлось бы придумать цену, которой не было, — и
        # сообщаем о расхождении отдельно.
        position.oversold += remaining
        position.quantity = Decimal("0")
        position.cost_basis = Decimal("0")

    position.realised += disposal.realised
    position.proceeds += proceeds
    position.disposals.append(disposal)
    return disposal


def replay(trades) -> Position:
    """Прогоняет журнал сделок по порядку.

    Сделки должны прийти уже отсортированными: порядок задаёт вызывающая
    сторона, потому что тай-брейк внутри дня — её дело (у сделок это
    day_order, затем id). Сортировать здесь значило бы решать за неё и
    молча ломать другой порядок.

    Каждая сделка — объект с полями side ("buy"/"sell"), quantity,
    price_per_unit, fee и, необязательно, trade_date.
    """
    position = Position()
    for trade in trades:
        side = getattr(trade.side, "value", trade.side)
        fee = trade.fee or Decimal("0")
        if side == "buy":
            buy(position, trade.quantity, trade.price_per_unit, fee, getattr(trade, "trade_date", None))
        else:
            sell(position, trade.quantity, trade.price_per_unit, fee)
    return position
