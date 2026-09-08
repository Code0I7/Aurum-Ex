"""aurum-ex: показывать ли копейки

Суммы округлялись до рубля везде — и в списке операций, и на обзоре. Для
итогов за год это разумно: копейки в 450 630 ₽ не несут никакого смысла и
только удлиняют число. Но в самой операции они и есть данные: 36,99
показанные как 37 — это уже не то, что записано, а список из таких строк не
сходится в сумму, и человек ищет ошибку там, где её нет.

Правильного ответа на все случаи нет, поэтому это переключатель. По
умолчанию включён: показать лишнее хуже, чем скрыть нужное, но врать хуже
обоих.

Revision ID: 0007_show_cents
Revises: 0006_base_units
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_show_cents"
down_revision = "0006_base_units"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("show_cents", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "show_cents")
