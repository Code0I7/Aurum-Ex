"""Справочник товаров и позиции чека.

Позиция и разбивка по категориям — разные вещи, и они сосуществуют.
Разбивка отвечает на вопрос «каким категориям принадлежат эти деньги» и
обязана сойтись с суммой транзакции до копейки. Позиция отвечает на вопрос
«что лежало в пакете» и сходиться не обязана ничему:

  * цена и сумма необязательны — помнить, что купили хлеб и молоко, не
    помня цен, обычное дело, и отказ такое хранить потерял бы память
    целиком;
  * сумма транзакции остаётся источником истины, а нераспределённый остаток
    показывается, а не подгоняется;
  * чек без позиций совершенно нормален — быстрый ввод остаётся одним
    действием.
"""
from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Единица измерения — подсказка, подставляемая в позицию при выборе
    # товара. Именно подсказка: в позиции её можно поменять, не трогая
    # справочник.
    #
    # Категории у товара нет и не должно быть. Она тут стояла и копировалась
    # в позицию чека, где её никто не читал: деньги считаются по категории
    # операции. Получалось поле, которое надо заполнять, которое ни на что
    # не влияет и которое приходится объяснять.
    unit_id: int | None = None
    barcode: str | None = Field(default=None, max_length=64)
    notes: str | None = None
    is_archived: bool = False


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit_id: int | None = None
    barcode: str | None = Field(default=None, max_length=64)
    notes: str | None = None
    is_archived: bool | None = None


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    unit_name: str | None = None
    # Сколько раз товар встречался в чеках и когда в последний раз. Список
    # товаров без этого — просто список слов: непонятно, что живое, а что
    # заведено однажды по ошибке.
    purchases: int = 0
    last_bought: date_ | None = None
    last_price_per_base_unit: Decimal | None = None
    # В каких единицах выражена цена выше: «74 ₽ / л» читается, а
    # «74 ₽ / ед.» заставляет догадываться, за что именно.
    base_unit_name: str | None = None
    # Сколько денег ушло на этот товар. Кривая цены отвечает на вопрос
    # «дорожает ли», а это — на «сколько мне это стоит»: полтинник за
    # батон незаметен, три тысячи за год на хлеб — уже разговор.
    #
    # Год скользящий, а не календарный: в январе календарный показывал бы
    # траты за две недели и выглядел бы падением там, где его нет.
    spent_total: Decimal = Decimal("0")
    spent_year: Decimal = Decimal("0")


class PricePoint(BaseModel):
    """Одна покупка товара: когда, почём, где."""

    date: date_
    # Цена за базовую единицу своего рода — грамм, миллилитр, штука. Именно
    # она делает 1,5 л за 120 ₽ и 500 мл за 55 ₽ сравнимыми.
    price_per_base_unit: Decimal
    quantity: Decimal
    unit_name: str | None
    amount: Decimal
    store_name: str | None
    transaction_id: int


class ProductPriceHistory(BaseModel):
    """Кривая цены по товару.

    Десять чеков со словом «хлеб» — десять несвязанных строк; десять позиций,
    указывающих на одну строку справочника, — кривая цены. Ради этого
    справочник товаров и нужен.
    """

    product_id: int
    product_name: str
    base_unit_name: str | None
    points: list[PricePoint]
    # Минимум, максимум и последняя цена за базовую единицу. Считаются здесь,
    # а не в интерфейсе: одно место на все способы показать цену.
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    last_price: Decimal | None = None
    # Изменение последней цены к первой, в процентах. None, когда точек
    # меньше двух: рост считать не от чего.
    change_percent: float | None = None


class TransactionItemInput(BaseModel):
    product_id: int | None = None
    # Название как в чеке. Хранится всегда, даже когда товар выбран из
    # справочника: в магазине он мог называться иначе, и это важно помнить.
    name: str = Field(min_length=1, max_length=200)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    unit_id: int | None = None
    # Цена за БАЗОВУЮ меру своего вида — за килограмм, за литр, за штуку.
    # Так написано на ценнике; цена за введённую единицу давала бы «0,074»
    # у пол-литра воды. Сумма считается как quantity × factor × price.
    price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    note: str | None = Field(default=None, max_length=200)


class TransactionItemRead(TransactionItemInput):
    """Позиция чека, как её отдают наружу.

    Ограничение на количество снято по той же причине, что и у операции:
    схема чтения обязана уметь показать всё, что лежит в базе. Нулевое
    количество из перенесённой таблицы иначе роняло бы весь список
    операций, а не только свою строку.
    """

    model_config = ConfigDict(from_attributes=True)

    quantity: Decimal | None = None

    id: int
    position: int
    product_name: str | None = None
    unit_name: str | None = None
