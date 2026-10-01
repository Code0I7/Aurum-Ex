"""aurum-ex: считать ли данное в долг тратой

Деньги, одолженные человеку, со счёта ушли — значит трата; но они
вернутся — значит не трата. Оба ответа честные, и выбирать между ними
должен владелец денег, а не приложение. Колонка хранит этот выбор.

Значение по умолчанию — «считать»: так итог за период сходится с
деньгами, и месяц, в котором со счетов ушло больше, чем пришло, не
выглядит сбережением.

Revision ID: 0027_lending_spending
Revises: 0026_credit_rates
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_lending_spending"
down_revision = "0026_credit_rates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default нужен существующим установкам: строка настроек там уже
    # есть, и без значения по умолчанию колонка легла бы пустой.
    op.add_column(
        "app_settings",
        sa.Column("lending_is_spending", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "lending_is_spending")
