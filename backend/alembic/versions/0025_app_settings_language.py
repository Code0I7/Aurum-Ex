"""aurum-ex: язык установки

Язык интерфейса до сих пор жил только в браузере, и сервер о нём не знал.
Из-за этого засев говорил по-русски всегда: единицы измерения на новой
установке заводились как «кг», «шт», «л» — даже у того, кто открыл
приложение по-английски. Переименовать их можно руками в справочнике, но
начинать знакомство с приложением с этого не должен никто.

Колонка хранит язык самой установки: его выбирают при первом запуске, он же
становится языком по умолчанию для браузера, в котором выбора ещё не
делали. Личный выбор в настройках остаётся сильнее — он и пишется сюда,
чтобы следующий телефон открылся на том же языке.

Revision ID: 0025_app_settings_language
Revises: 0024_currency_cbr_code
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_app_settings_language"
down_revision = "0024_currency_cbr_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default нужен существующим установкам: строка настроек там уже
    # есть, и без значения по умолчанию колонка легла бы пустой.
    op.add_column(
        "app_settings",
        sa.Column("language", sa.String(2), nullable=False, server_default="ru"),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "language")
