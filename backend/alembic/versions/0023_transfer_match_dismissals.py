"""aurum-ex: отказы от склейки перевода, записанного дважды

Перевод между своими счетами заносят по выпискам, а выписок две — по одной
на банк. Приложение находит пары «ушло с одного моего счёта — пришло на
другой» и предлагает склеить их в один перевод, но само не склеивает
никогда: совпадение суммы и даты бывает и честным.

Здесь хранится ответ «это разные». Без него отклонённая пара возвращалась бы
в список при каждой загрузке.

Revision ID: 0023_transfer_match_dismissals
Revises: 0022_counterparty_splits
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_transfer_match_dismissals"
down_revision = "0022_counterparty_splits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transfer_match_dismissals",
        # Меньший номер первым: одна пара — одна строка. Удалённая операция
        # уносит решения о себе.
        sa.Column(
            "first_id",
            sa.Integer(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "second_id",
            sa.Integer(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            primary_key=True,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("transfer_match_dismissals")
