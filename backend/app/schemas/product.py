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
    # Количество и единица последней покупки. Подставляются в новую позицию
    # при выборе товара: одно и то же число в каждом чеке человек вводит
    # ровно до тех пор, пока не перестаёт заполнять чек вообще.
    #
    # Единица здесь может отличаться от unit_id самого товара: в справочнике
    # записана обычная мера, а в последней покупке — та, что стояла в чеке.
    # Подставлять надо вторую: чек заполняют по чеку.
    last_quantity: Decimal | None = None
    last_unit_id: int | None = None
    # Размер упаковки для подстановки — только когда он устоялся: последние
    # две покупки с записанным размером совпали. У молока в литровых пакетах
    # совпадают всегда, у сыра, расфасованного в магазине, — никогда, и
    # подставлять там нечего: вес каждой упаковки свой.
    last_pack_size: Decimal | None = None
    last_pack_unit_id: int | None = None
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
    # Цена за базовую единицу своего рода — килограмм, литр, штука. Именно
    # она делает 1,5 л за 120 ₽ и 500 мл за 55 ₽ сравнимыми.
    price_per_base_unit: Decimal
    quantity: Decimal
    unit_name: str | None
    # Размер упаковки, если он был записан: строка читается как «2 шт ×
    # 0,9 л». Без него штуки остались бы штуками.
    pack_size: Decimal | None = None
    pack_unit_name: str | None = None
    amount: Decimal
    store_name: str | None
    transaction_id: int


class PriceSeries(BaseModel):
    """Кривая цены в одной мере.

    Их у товара столько, сколько мер в нём встретилось. Смешивать нельзя:
    штука и килограмм — разные величины, и одна кривая на обе показывала
    падение цены на 91% там, где человек просто записал покупку по-другому.
    """

    # Род меры: mass, volume, count… Пусто, когда единицы у покупки не было
    # вовсе — тогда цена считается за то, что человек написал количеством.
    unit_kind: str | None = None
    base_unit_name: str | None = None
    points: list[PricePoint]
    # Минимум, максимум и последняя цена за базовую единицу. Считаются здесь,
    # а не в интерфейсе: одно место на все способы показать цену.
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    last_price: Decimal | None = None
    # Изменение последней цены к первой, в процентах. None, когда точек
    # меньше двух: рост считать не от чего.
    change_percent: float | None = None


class ProductPriceHistory(BaseModel):
    """Кривая цены по товару.

    Десять чеков со словом «хлеб» — десять несвязанных строк; десять позиций,
    указывающих на одну строку справочника, — кривая цены. Ради этого
    справочник товаров и нужен.
    """

    product_id: int
    product_name: str
    # Кривые по мерам, сначала та, в которой покупок больше: ею человек и
    # пользуется, а вторая — след того раза, когда записал иначе.
    series: list[PriceSeries] = []
    # Покупки, у которых цену за меру посчитать не из чего — без цены или
    # без количества. В кривую они не идут, но молчать о них нельзя: иначе
    # непонятно, почему покупок восемь, а точек пять.
    unmeasured: int = 0


class TransactionItemInput(BaseModel):
    product_id: int | None = None
    # Название как в чеке. Хранится всегда, даже когда товар выбран из
    # справочника: в магазине он мог называться иначе, и это важно помнить.
    name: str = Field(min_length=1, max_length=200)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    unit_id: int | None = None
    # Размер одной упаковки: «2 шт × 0,9 л». Мост между штуками и мерой —
    # без него первое со вторым несравнимо. Необязателен: у развесного
    # товара, расфасованного в магазине, вес каждой упаковки свой, и
    # забытый вес не повод придумывать его из прошлой покупки.
    pack_size: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    pack_unit_id: int | None = None
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
    pack_size: Decimal | None = None

    id: int
    position: int
    product_name: str | None = None
    unit_name: str | None = None
