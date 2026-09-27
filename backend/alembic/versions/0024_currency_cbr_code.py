"""aurum-ex: внутренний код валюты у источника курсов

Источник отдаёт историю одной валюты за диапазон дат одним обращением, но
только по своему внутреннему коду («R01235» у доллара), а не по буквенному.
Без истории динамика курса считалась не за день, а «с 19 сентября» — с той
даты, когда курс последний раз загружали.

Код приходит в том же ответе, что и котировки, поэтому колонка заполняется
сама при обычной загрузке курсов и остаётся пустой, пока за ними не ходили.

Revision ID: 0024_currency_cbr_code
Revises: 0023_transfer_match_dismissals
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_currency_cbr_code"
down_revision = "0023_transfer_match_dismissals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("currencies", sa.Column("cbr_code", sa.String(12), nullable=True))


def downgrade() -> None:
    op.drop_column("currencies", "cbr_code")
