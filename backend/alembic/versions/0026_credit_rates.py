"""aurum-ex: матрица ставок и минимальный платёж процентом

Одной ставки на кредитную карту не хватает. В тарифе их семь: покупки в
льготном периоде под ноль, покупки без него под 39,9%, снятие наличных под
59,9%, платы под те же 59,9% — и какая применится, зависит от того, что за
операция и когда она была. Одно поле «ставка» заставляло выбирать из них
одну и забывать остальные ровно тогда, когда они понадобятся.

Минимальный платёж банки тоже задают не суммой, а правилом: «не более 8% от
задолженности, минимум 600 рублей». Фиксированное число рядом с растущим
долгом устаревает в первый же месяц.

Revision ID: 0026_credit_rates
Revises: 0025_app_settings_language
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_credit_rates"
down_revision = "0025_app_settings_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "credit_terms",
        sa.Column("minimum_payment_percent", sa.Numeric(5, 2), nullable=True),
    )
    op.create_table(
        "credit_rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Ссылка на условия, а не на счёт: ставки без условий не существуют,
        # и удаление условий уносит их с собой.
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("credit_terms.account_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("percent", sa.Numeric(6, 3), nullable=False),
        # Условие, при котором ставка применяется: «с 31-го дня», «в первые
        # 30 дней». Свободная строка: у каждого банка своя нарезка.
        sa.Column("condition", sa.String(200), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("credit_rates")
    op.drop_column("credit_terms", "minimum_payment_percent")
