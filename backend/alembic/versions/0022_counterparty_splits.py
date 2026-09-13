"""aurum-ex: разбивка операции между людьми

Долг вернули трое одним переводом. В выписке банка это одна операция, и
три записи в приложении означали бы, что оно перестало сходиться с
выпиской — ровно та причина, по которой у операции когда-то появилась
разбивка по категориям.

Отдельная таблица, а не переиспользование той, что делит по категориям.
Оси независимы: одна отвечает на «на что», вторая на «от кого». В одной
таблице «разделено и по людям, и по категориям» стало бы невыразимым, а
правила «строк не меньше двух» и «одиночное поле должно быть пустым»
начали бы означать две разные вещи сразу.

Вид расчёта (заём, безвозвратно, транзит) остаётся на самой операции:
трое, вернувшие долг, вернули именно долг. Понадобится свой у каждого —
добавится колонкой сюда же, и старые строки продолжат брать общий.

Revision ID: 0022_counterparty_splits
Revises: 0021_goal_dates
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_counterparty_splits"
down_revision = "0021_goal_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transaction_counterparty_splits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # SET NULL, как и у категории в разбивке: удаление человека не
        # должно ломать чтение операции, в которой он когда-то был.
        sa.Column(
            "counterparty_id",
            sa.Integer(),
            sa.ForeignKey("counterparties.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("transaction_counterparty_splits")
