"""aurum-ex: у плана несколько периодов вместо одной суммы

Сумма и даты жили прямо в плане, и смена тарифа означала второй план: та же
категория, тот же вид, другая сумма, другие даты. За несколько лет от
«связи 700 ₽» оставался десяток записей с одинаковым названием, и понять,
какая действует сейчас, можно было только сверив даты у всех. Список планов
превращался в список версий одного плана.

Теперь план — это категория и способ счёта, а суммы лежат внутри списком.
У каждого отрезка своя заметка: «подорожал тариф», «сменил оператора» —
ответ на вопрос «почему тут другое число», который через год не вспомнит
никто.

Существующие планы переносятся как есть: один план — один период. Ничего не
теряется и не склеивается, разбирать накопившееся вручную не требуется.

Revision ID: 0011_plan_periods
Revises: 0010_drop_item_product_category
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_plan_periods"
down_revision = "0010_drop_item_product_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_plan_periods_plan_id", "plan_periods", ["plan_id"])

    # Перенос до удаления колонок: каждый существующий план становится
    # планом с одним периодом. Заметка остаётся у плана — она была написана
    # про него целиком, а не про смену суммы, которой ещё не было.
    op.execute(
        """
        INSERT INTO plan_periods (plan_id, amount, valid_from, valid_to)
        SELECT id, amount, valid_from, valid_to FROM plans
        """
    )

    op.drop_column("plans", "amount")
    op.drop_column("plans", "valid_from")
    op.drop_column("plans", "valid_to")


def downgrade() -> None:
    # Обратно берётся самый ранний период: он и был исходной записью до
    # разделения. Остальные при откате теряются — план с тремя суммами в
    # одну колонку не помещается, и делать вид, что помещается, хуже, чем
    # сказать это прямо.
    op.add_column("plans", sa.Column("amount", sa.Numeric(18, 2), nullable=True))
    op.add_column("plans", sa.Column("valid_from", sa.Date(), nullable=True))
    op.add_column("plans", sa.Column("valid_to", sa.Date(), nullable=True))
    op.execute(
        """
        UPDATE plans SET
            amount = source.amount,
            valid_from = source.valid_from,
            valid_to = source.valid_to
        FROM (
            SELECT DISTINCT ON (plan_id) plan_id, amount, valid_from, valid_to
            FROM plan_periods ORDER BY plan_id, valid_from
        ) AS source
        WHERE plans.id = source.plan_id
        """
    )
    # Планы без периодов существовать не могут, но на случай ручной правки
    # базы ставим что-нибудь непротиворечивое, иначе NOT NULL не наложится.
    op.execute("UPDATE plans SET amount = 0 WHERE amount IS NULL")
    op.execute("UPDATE plans SET valid_from = CURRENT_DATE WHERE valid_from IS NULL")
    op.alter_column("plans", "amount", nullable=False)
    op.alter_column("plans", "valid_from", nullable=False)

    op.drop_index("ix_plan_periods_plan_id", table_name="plan_periods")
    op.drop_table("plan_periods")
