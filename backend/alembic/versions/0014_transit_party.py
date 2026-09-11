"""aurum-ex: у транзита есть вторая сторона

Транзит проходит между двумя людьми, а поле для человека в операции было
одно. Брат передаёт на покупки для мамы, покупки делаются для мамы — в
записи оказывались Брат у прихода и Мама у расхода, и сложить их было не по
чему. Приложение писало «Брату осталось 4 500» и «Маме недодал 4 870»: оба
числа бессмысленны, потому что стороны разные.

Теперь у транзитной операции две стороны:

  приход  — counterparty это кто передал, transit_party это для кого;
  расход  — counterparty это кому ушло, transit_party это чьи деньги.

Сложение идёт по «для кого»: получено для мамы минус потрачено на маму. Брат
в расчётах не появляется вовсе — он источник, а не сторона: ни он никому не
должен, ни ему.

Поле только для транзита. У подарка и займа второй стороны нет: там деньги
и правда между двумя.

Revision ID: 0014_transit_party
Revises: 0013_store_group
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_transit_party"
down_revision = "0013_store_group"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("transit_party_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "transactions_transit_party_id_fkey",
        "transactions",
        "counterparties",
        ["transit_party_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_transactions_transit_party_id", "transactions", ["transit_party_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_transit_party_id", table_name="transactions")
    op.drop_constraint("transactions_transit_party_id_fkey", "transactions", type_="foreignkey")
    op.drop_column("transactions", "transit_party_id")
