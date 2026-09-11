"""aurum-ex: у позиции чека и у товара больше нет категории

Категория стояла в трёх местах, а считалась в одном.

  * у операции — по ней и только по ней считают отчёты, бюджет и планы;
  * у сплита — то же самое, когда одна операция делится между статьями;
  * у позиции чека — хранилась, редактировалась и не читалась НИКЕМ
    (services/category_rollup.py суммирует операции и сплиты, и всё);
  * у товара в справочнике — копировалась в позицию при выборе товара, то
    есть питала предыдущий пункт.

Получалось поле, которое надо заполнять, которое ни на что не влияет и
которое приходится объяснять. Хуже того — на него смотрели и делали
выводы: «я же проставил категории у позиций, почему в отчёте пусто».

Товар отвечает на вопрос «что купили», категория — «куда ушли деньги».
Разложить чек по статьям можно сплитами, для этого они и есть.

Если однажды понадобится считать деньги по позициям — это будет другая
задача со своим решением проблемы двойного счёта (позиция и операция
указывали бы на категорию одновременно), и начинать её надо будет не с
колонки, оставшейся от прошлой попытки.

Revision ID: 0010_drop_item_product_category
Revises: 0009_plan_weekdays_only
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_drop_item_product_category"
down_revision = "0009_plan_weekdays_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("transaction_items", "category_id")
    op.drop_column("products", "category_id")


def downgrade() -> None:
    # Колонки вернутся пустыми: значения не восстанавливаются, и это не
    # упущение. Откат схемы — не откат данных, а обещать обратное хуже,
    # чем сказать прямо.
    op.add_column(
        "products",
        sa.Column("category_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "products_category_id_fkey", "products", "categories", ["category_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column(
        "transaction_items",
        sa.Column("category_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "transaction_items_category_id_fkey",
        "transaction_items",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )
