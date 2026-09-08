"""aurum-ex: настройки вида по умолчанию

Что показывать при открытии приложения, человек выбирает один раз, а не
каждый сеанс заново. Три вещи, о которых спрашивали прямо:

  * период дашборда — месяц, год или всё время;
  * сколько операций подгружать за раз (двадцать — мало, если история за
    четыре года);
  * склеивать ли одинаковые траты дня и рисовать ли разделители дней.

Хранится на сервере, а не в браузере: установка однопользовательская, и
настройка, сделанная на ноутбуке, должна действовать и с телефона.

Revision ID: 0002_view_defaults
Revises: 0001_aurum_ex_base
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_view_defaults"
down_revision = "0001_aurum_ex_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default обязателен: строка настроек уже существует, и без него
    # NOT NULL не применить к заполненной таблице.
    op.add_column(
        "app_settings",
        sa.Column("default_dashboard_range", sa.String(length=10), nullable=False, server_default="year"),
    )
    op.add_column(
        "app_settings",
        sa.Column("default_page_size", sa.Integer(), nullable=False, server_default="50"),
    )
    op.add_column(
        "app_settings",
        sa.Column("group_repeats_by_default", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "app_settings",
        sa.Column("day_dividers_by_default", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "day_dividers_by_default")
    op.drop_column("app_settings", "group_repeats_by_default")
    op.drop_column("app_settings", "default_page_size")
    op.drop_column("app_settings", "default_dashboard_range")
