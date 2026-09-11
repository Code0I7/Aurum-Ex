"""aurum-ex: план по будням календаря

У ежедневного плана было два режима: календарные дни месяца и отработанные
дни из work_periods. Второй требует вводить дни руками и появляется задним
числом — он для вахты и смен.

Пятидневке нужен третий: будни календаря. Они известны на годы вперёд и
ничего вводить не требуют, а столовая по выходным не работает ровно так же.
Раньше человек ставил «по отработанным», вводил число — и любая ошибка в нём
превращала план в неправдоподобный: два дня вместо двадцати дают 400 ₽ там,
где потрачено несколько тысяч.

Признаки взаимоисключающие — проверяется в схеме, не в базе: два разных
числа дней на один месяц означали бы выбор молча за человека.

Revision ID: 0009_plan_weekdays_only
Revises: 0008_transaction_indexes
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_plan_weekdays_only"
down_revision = "0008_transaction_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("weekdays_only", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("plans", "weekdays_only")
