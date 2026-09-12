"""aurum-ex: у перевода между валютами две суммы

Перевод записан одной строкой, со стороны отправителя: сумма, валюта и счёт
получателя. Пока обе карты в одной валюте, этого достаточно — сколько ушло,
столько и пришло.

Между валютами это перестаёт быть правдой. Сто евро уходят с евровой карты,
а на рублёвую приходит не сто, а девять с чем-то тысяч — и сколько именно,
решает банк своим курсом и своей комиссией. Вывести это число из курса ЦБ
нельзя: оно и не равно ему, и не обязано.

Поэтому вторая сумма хранится как данные, а не считается: её вводит человек,
переписав из выписки. Три колонки, все пустые у обычного перевода — там
вторая сумма равна первой, и хранить одно число дважды незачем.

Revision ID: 0020_transfer_two_amounts
Revises: 0019_watchlist_defaults
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_transfer_two_amounts"
down_revision = "0019_watchlist_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions", sa.Column("transfer_amount", sa.Numeric(18, 2), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("transfer_currency", sa.String(3), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("transfer_amount_base", sa.Numeric(18, 2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("transactions", "transfer_amount_base")
    op.drop_column("transactions", "transfer_currency")
    op.drop_column("transactions", "transfer_amount")
