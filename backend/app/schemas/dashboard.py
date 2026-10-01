from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field


class CategoryBreakdownChildItem(BaseModel):
    """One subcategory's (or the parent's own direct, un-subcategorized)
    share of a CategoryBreakdownItem's total — see
    services/category_rollup.py's CategoryRollupChildItem."""

    category_id: int
    name: str
    color: str
    icon: str | None
    amount: Decimal
    # Своя разбивка строки — только внутри доли «Прочее». Там строка — целая
    # категория верхнего уровня, свёрнутая в «Прочее», и у неё могут быть
    # подкатегории, как у любой категории основного списка. Без них «Еда»,
    # попавшая в «Прочее», открывалась бы одной суммой без разбивки.
    children: list["CategoryBreakdownChildItem"] = Field(default_factory=list)


class CategoryBreakdownItem(BaseModel):
    category_id: int | None
    name: str
    color: str
    icon: str | None
    amount: Decimal
    percent: float
    # Populated only when this slice's spend came from more than one
    # distinct category (subcategories, or a mix of the parent itself and
    # its children) — e.g. a receipt split across "Groceries" subcategories.
    children: list[CategoryBreakdownChildItem] = Field(default_factory=list)


class AccountBalanceItem(BaseModel):
    """Остаток на счёте — всегда текущий, а не на конец периода.

    Вопрос «сколько у меня сейчас» не зависит от того, какой период выбран
    сверху, и подменять ответ остатком на конец марта значило бы врать
    ровно тому, кто смотрит на дашборд, чтобы понять, сколько у него денег.
    """

    account_id: int
    name: str
    balance: Decimal
    # Валюта счёта и тот же остаток в валюте установки по сегодняшнему
    # курсу. Без валюты обзор подписывал каждый остаток значком валюты
    # установки: сто евро выглядели как сто рублей. Пересчёт нужен второй
    # строкой и для итога сверху — сложить евро с рублями иначе нельзя.
    currency: str = ""
    balance_base: Decimal = Decimal("0")
    reserved: Decimal
    available: Decimal
    nature: str


class LargestTransactionItem(BaseModel):
    id: int
    date: date_
    # Может быть пустым: описание операции необязательно. Схема показа
    # обязана уметь показать всё, что лежит в базе, — иначе одна строка без
    # описания роняет целый экран. Это уже случалось трижды, каждый раз с
    # другим полем и другим экраном.
    description: str | None = None
    amount: Decimal
    category_name: str | None
    account_name: str


class MonthPoint(BaseModel):
    year: int
    month: int
    income: Decimal
    expense: Decimal
    net: Decimal


class DayPoint(BaseModel):
    """День внутри выбранного месяца. Пустой список, когда выбран не месяц:
    за год дневных столбцов 365, и ни один из них ничего не показывает."""

    date: date_
    income: Decimal
    expense: Decimal
    net: Decimal


class DashboardSummary(BaseModel):
    year: int
    month: int
    # Границы периода, за который посчитаны суммы. Отдаются наружу, потому
    # что при выборе «за всё время» интерфейс сам их не знает.
    start_date: date_ | None = None
    end_date: date_ | None = None
    real_income: Decimal
    spent: Decimal
    net: Decimal
    transferred_out: Decimal
    spending_by_category: list[CategoryBreakdownItem]
    # Доходы по категориям — тем же правилом, что и расходы: семь крупнейших
    # и доля «Прочее» со свёрнутыми внутри.
    income_by_category: list[CategoryBreakdownItem] = []

    # Остатки по счетам: «сколько у меня сейчас и где».
    accounts: list[AccountBalanceItem] = []
    # Заработок за час работы. None, когда за период не введено ни часа:
    # делить на ноль нечестнее, чем не показывать.
    hours_worked: Decimal | None = None
    earned_per_hour: Decimal | None = None
    # Самые крупные траты периода — то, что обычно и объясняет, куда ушли
    # деньги, лучше любой диаграммы.
    largest_expenses: list[LargestTransactionItem] = []
    # Помесячная картина внутри периода.
    monthly: list[MonthPoint] = []
    daily: list[DayPoint] = []
