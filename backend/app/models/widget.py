"""A dashboard tile, described as data rather than written as code.

The distinction decides how much work a later widget builder costs. If tiles
are hard-coded components, letting the user assemble their own means writing
that feature from scratch and throwing away what exists. If every tile is
already a row saying "какой график, по каким данным, за какой период", then
the ready-made dashboard is just a seeded list of those rows, and the builder
is a screen that edits them.

So the shipped dashboard is seeded from this table, and the builder — второй
этап той же работы — adds nothing to the model.

`config` holds the per-type settings as JSON: which categories to include,
which accounts, how many slices before the rest fold into "прочее". JSON
rather than columns because every widget type wants different keys, and a
table with thirty mostly-null columns would be worse in every way.
"""
from typing import Any

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class DashboardWidget(Base, TimestampMixin):
    __tablename__ = "dashboard_widgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Тип плитки: "cash_flow", "category_pie", "net_worth", "budget_status".
    # Строка, а не enum: добавление нового типа не должно требовать миграции.
    widget_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Период: "current_month" — всегда текущий, "current_year", либо
    # конкретный "2026-03". Автоматическая смена месяца, о которой шла речь,
    # это и есть первый вариант.
    period: Mapped[str] = mapped_column(String(30), nullable=False, default="current_month")

    # Место на сетке: строка, колонка и ширина в колонках.
    row: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
