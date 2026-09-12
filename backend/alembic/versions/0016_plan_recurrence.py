"""aurum-ex: у плана появилось расписание

Видов плана было три — разовый, ежемесячный и ежедневный, — и всё, что в
них не укладывалось, приходилось заводить руками: «раз в квартал» четырьмя
разовыми планами, «каждые две недели» никак.

Теперь вид — это частота (день, неделя, месяц, год), а к ней шаг
`repeat_every` и уточнения: по каким дням недели, по каким числам, каким по
счёту днём недели в месяце, в каких месяцах.

Значения старых видов переименованы под новые: MONTHLY → MONTH, DAILY →
DAY. Шаг у них единица, поэтому считаются они ровно так же, как считались.

`weekdays_only` заменён на `skip_weekends`: смысл тот же — будни календаря,
без праздников, — но работает и с шагом больше единицы, а прежняя галочка
жила только у ежедневного плана с шагом в один день.

Множественные значения лежат массивами, а не строкой через запятую: в них
складывают числа, и разбирать строку пришлось бы на каждом чтении.

Revision ID: 0016_plan_recurrence
Revises: 0015_counterparty_group
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0016_plan_recurrence"
down_revision = "0015_counterparty_group"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("repeat_every", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("plans", sa.Column("weekdays", ARRAY(sa.Integer()), nullable=True))
    op.add_column("plans", sa.Column("month_day_mode", sa.String(20), nullable=True))
    op.add_column("plans", sa.Column("month_days", ARRAY(sa.Integer()), nullable=True))
    op.add_column("plans", sa.Column("nth_weekday", sa.Integer(), nullable=True))
    op.add_column("plans", sa.Column("months", ARRAY(sa.Integer()), nullable=True))
    op.add_column(
        "plans", sa.Column("skip_weekends", sa.Boolean(), nullable=False, server_default="false")
    )

    # Старые виды под новыми именами. Шаг у них единица, значит и считаются
    # они по-прежнему: ежемесячный — раз в месяц, ежедневный — каждый день.
    op.execute("UPDATE plans SET kind = 'MONTH' WHERE kind = 'MONTHLY'")
    op.execute("UPDATE plans SET kind = 'DAY' WHERE kind = 'DAILY'")
    op.execute("UPDATE plans SET skip_weekends = weekdays_only")
    op.drop_column("plans", "weekdays_only")


def downgrade() -> None:
    op.add_column(
        "plans", sa.Column("weekdays_only", sa.Boolean(), nullable=False, server_default="false")
    )
    # Обратно переносится только то, что старый вид умел выразить: будни у
    # ежедневного плана с шагом в один день. Всё остальное расписание в трёх
    # видах не помещается и теряется — поэтому откат тут односторонний по
    # смыслу, а не по схеме.
    op.execute("UPDATE plans SET weekdays_only = skip_weekends WHERE kind = 'DAY' AND repeat_every = 1")
    op.execute("UPDATE plans SET kind = 'MONTHLY' WHERE kind = 'MONTH'")
    op.execute("UPDATE plans SET kind = 'DAILY' WHERE kind IN ('DAY', 'WEEK')")
    op.execute("UPDATE plans SET kind = 'MONTHLY' WHERE kind = 'YEAR'")

    op.drop_column("plans", "skip_weekends")
    op.drop_column("plans", "months")
    op.drop_column("plans", "nth_weekday")
    op.drop_column("plans", "month_days")
    op.drop_column("plans", "month_day_mode")
    op.drop_column("plans", "weekdays")
    op.drop_column("plans", "repeat_every")
