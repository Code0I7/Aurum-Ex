"""aurum-ex: считать ли личные вещи в разрезе по риску

Уровни риска существуют ради правила «столько-то капитала размещено без
риска, не больше столько-то под риском». Компьютер, на котором работают, —
не размещение, и предупреждение о рискованном размещении срабатывало на
личные вещи. Правильного ответа нет: обесценивается и телефон. Колонка
хранит этот выбор.

Значение по умолчанию — «считать»: так разрез остаётся тем, чем был, и
обновление ничего не меняет у тех, кто об этом не просил.

Revision ID: 0028_risk_personal_use
Revises: 0027_lending_spending
"""
from alembic import op
import sqlalchemy as sa

revision = "0028_risk_personal_use"
down_revision = "0027_lending_spending"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default нужен существующим установкам: строка настроек там уже
    # есть, и без значения по умолчанию колонка легла бы пустой.
    op.add_column(
        "app_settings",
        sa.Column("risk_counts_personal_use", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "risk_counts_personal_use")
