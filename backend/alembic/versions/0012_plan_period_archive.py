"""aurum-ex: отрезок плана можно убрать с глаз

Список отрезков растёт и не убывает: тариф менялся четыре раза за три года —
в форме четыре строки, из которых живая одна. Прошлые нужны (без них
таблица прошлых лет соврёт), но каждый раз листать их незачем.

Пометка — только про показ. Помеченный отрезок считается ровно так же и в
таблице года стоит на своём месте; он просто не мозолит глаза в форме, пока
не попросят показать. Никакой логики «архивное не учитывается» здесь нет и
быть не должно: спрятать число и перестать его считать — разные вещи, и
путать их в учёте нельзя.

Revision ID: 0012_plan_period_archive
Revises: 0011_plan_periods
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_plan_period_archive"
down_revision = "0011_plan_periods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plan_periods",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("plan_periods", "is_archived")
