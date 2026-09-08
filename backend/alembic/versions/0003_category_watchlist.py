"""aurum-ex: список наблюдения за категориями

В исходной таблице был отдельный лист «Отследить»: несколько выбранных
подкатегорий, двенадцать месяцев и переключатели «Вкл/Выкл». Смысл в том,
чтобы держать на виду не весь список категорий, а те несколько, за которыми
человек сейчас следит, — «Сладкое», «Такси», «Подписки».

Признак стоит на самой категории, а не в отдельной таблице связей: наблюдают
за категорией, а не за парой «категория — год», и одна колонка честно
описывает это отношение. Отдельная таблица понадобилась бы, если бы список
наблюдения был у каждого человека свой, — установка однопользовательская.

Revision ID: 0003_category_watchlist
Revises: 0002_view_defaults
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_category_watchlist"
down_revision = "0002_view_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default обязателен: категории уже есть, и без него NOT NULL не
    # применить к заполненной таблице.
    op.add_column(
        "categories",
        sa.Column("is_watched", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("categories", "is_watched")
