"""A spending/income category, colored so it maps 1:1 to a dashboard chart slot."""
from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CategoryKind


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[CategoryKind] = mapped_column(
        Enum(CategoryKind, name="category_kind", native_enum=False, length=10), nullable=False
    )
    # Lucide icon name rendered in the frontend (kept as a plain string so new
    # icons don't require a migration).
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Hex color drawn from the dataviz skill's validated categorical palette.
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    # Fixed slot ordering keeps the donut chart's category order stable across renders.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Список наблюдения. В исходной таблице был лист «Отследить»: несколько
    # выбранных подкатегорий по месяцам, чтобы держать на виду не весь
    # список, а те, за которыми человек следит прямо сейчас.
    #
    # Признак на самой категории, а не отдельная таблица связей: наблюдают
    # за категорией, а не за парой «категория — год». Планирование читает
    # его в services/plan_service.py.
    is_watched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Ссылка на саму себя: дерево произвольной глубины. Одноуровневое
    # ограничение оригинального Aurum снято — «Продукты → Молочное → Сыр»
    # законны, и ветку с детьми можно перенести целиком. Границы ставит
    # routes/categories.py: не глубже MAX_DEPTH уровней, без циклов и без
    # смешения доходов с расходами в одной ветке.
    #
    # Подъём суммы к корню ветки НЕ выражается через coalesce(parent_id, id):
    # это один шаг, а корень может быть выше. Ходить по дереву умеет
    # services/category_tree.py, и делать это надо через него.
    #
    # SET NULL: удаление родителя поднимает детей на верхний уровень, а не
    # удаляет их вместе с историей.
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
    parent: Mapped["Category | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Category"]] = relationship(back_populates="parent")
