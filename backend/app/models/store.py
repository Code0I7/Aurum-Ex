"""A shop or point of sale where a purchase happened.

Spreadsheets often carry a list of shops in their settings sheet and no
column for it on the transactions sheet — so the list gets filled in and
never used, and comparing prices between shops stays impossible no matter
how carefully the rows are typed.
Here the link is real: store on the transaction, product and price on the
line item, and "this loaf costs 45 ₽ here and 52 ₽ there" falls out
of data that is already being entered.

Optional on a transaction. A subscription or a bank fee has no shop, and
demanding one would just teach the user to pick a meaningless value.
"""
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Store(Base, TimestampMixin):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    # Free-form: "улица и дом", "онлайн", город — нужен только человеку,
    # который потом вспоминает, тот ли это магазин.
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Полка, на которую человек сам кладёт запись: «продуктовые»,
    # «маркетплейсы», «игровые». Живёт только на странице справочников — ни
    # в отчёты, ни в подстановку не идёт.
    #
    # Свободная строка, а не список: набор полок у каждого свой, и
    # предлагать готовый значит навязать чужой. Имя колонки с суффиксом,
    # потому что `group` в SQL — ключевое слово.
    group_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
