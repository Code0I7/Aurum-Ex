"""aurum-ex: сумма в валюте установки может быть пустой

Если курса на дату операции нет, приложение молча брало единицу: покупка на
50 $ становилась 50 ₽ в отчётах. Число выглядит как обычное, ни пометки, ни
ошибки — и заметно это только по годовым итогам, когда искать причину уже
негде.

Пустое значение говорит правду: «пересчитать пока не из чего». Такая
операция сохраняется целиком, видна в списке с пометкой и не входит в итоги,
а в отчёте под ними сказано, сколько таких пропущено. Курс на прошедший день
не меняется никогда — ЦБ отдаёт архив с 1992 года, — поэтому дотянуть его
потом и пересчитать не значит переписать прошлое: это значит записать его
впервые.

Колонка курса тоже становится пустой: единица в ней была тем же самым
враньём, только в другом поле.

Revision ID: 0018_amount_base_nullable
Revises: 0017_item_pack_size
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_amount_base_nullable"
down_revision = "0017_item_pack_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("transactions", "amount_base", existing_type=sa.Numeric(18, 2), nullable=True)
    op.alter_column(
        "transactions", "exchange_rate", existing_type=sa.Numeric(20, 10), nullable=True
    )


def downgrade() -> None:
    # Обратно колонки требуют значения, а у непересчитанных операций его нет.
    # Единица здесь — то же враньё, ради ухода от которого всё и делалось, но
    # иного значения у отката нет.
    op.execute("UPDATE transactions SET amount_base = amount WHERE amount_base IS NULL")
    op.execute("UPDATE transactions SET exchange_rate = 1 WHERE exchange_rate IS NULL")
    op.alter_column(
        "transactions", "exchange_rate", existing_type=sa.Numeric(20, 10), nullable=False
    )
    op.alter_column("transactions", "amount_base", existing_type=sa.Numeric(18, 2), nullable=False)
