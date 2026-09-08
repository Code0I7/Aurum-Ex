"""A thing that gets bought repeatedly — "хлеб чёрный городской", "молоко
3.2%", "боевой пропуск" — with the category and unit it usually comes in.

Two jobs. First, autofill: picking a product fills in its category, so the
user stops choosing from a 166-item subcategory list they cannot remember.
That was the plan in the source spreadsheet too — it even reserved a named
range called `Продукты` — but the column was left empty and the feature
never existed.

Second, price history: ten receipts mentioning "хлеб" as free text are ten
unrelated strings, while ten line items pointing at one product row form a
price curve. This is the difference between "динамика цен на товар" working
and not working, and it is why the product reference has to exist before
line items are worth entering.
"""
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    # Подставляется в позицию чека при выборе товара. SET NULL, а не
    # CASCADE: удаление категории не должно уносить с собой товар вместе с
    # накопленной по нему историей цен.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    # Единица, в которой этот товар обычно покупают: молоко — литры, хлеб —
    # штуки. Тоже лишь подсказка, в позиции её можно поменять.
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), nullable=True)

    # Штрихкод — необязателен, но если он есть, товар находится сканером
    # телефона без набора названия руками.
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    category: Mapped["Category | None"] = relationship()
    unit: Mapped["Unit | None"] = relationship()
