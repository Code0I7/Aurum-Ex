"""aurum-ex: у позиции чека есть размер упаковки

Один и тот же товар человек считает то упаковками, то граммами: молоко
сегодня «1 шт», завтра «900 мл». Приложение переводило количество в базовую
меру через коэффициент единицы, но род единицы при этом не смотрело вовсе —
и штуки попадали на одну ось с килограммами. Шоколад, купленный раз как
«90 г за 89 ₽» (989 ₽/кг) и раз как «1 шт за 89 ₽» (89 ₽/шт), показывал на
графике падение цены на 91%, которого не было.

Размер упаковки лежит в позиции, а не в товаре, и это главное решение
здесь. В товаре он был бы одним числом на всю историю: производитель ужал
литр до 900 мл — и прошлые покупки задним числом пересчитались бы по новому
размеру, спрятав ровно то подорожание, ради которого учёт цен и ведут. В
позиции он остаётся тем, что было в день покупки, навсегда.

Revision ID: 0017_item_pack_size
Revises: 0016_plan_recurrence
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_item_pack_size"
down_revision = "0016_plan_recurrence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transaction_items", sa.Column("pack_size", sa.Numeric(18, 4), nullable=True))
    op.add_column("transaction_items", sa.Column("pack_unit_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "transaction_items_pack_unit_id_fkey",
        "transaction_items",
        "units",
        ["pack_unit_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "transaction_items_pack_unit_id_fkey", "transaction_items", type_="foreignkey"
    )
    op.drop_column("transaction_items", "pack_unit_id")
    op.drop_column("transaction_items", "pack_size")
