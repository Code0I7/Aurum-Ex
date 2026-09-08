"""aurum-ex: необязательное описание и имущество личного пользования

**Описание операции больше не обязательно.** В исходной таблице это была
вторая строка записи, а не заметка к ней: у большинства покупок сказать
сверх категории нечего, и требовать текст значило заставлять придумывать
его. Заодно уходит поле «заметка» — оно описывало ровно то же самое
вторым способом. На момент миграции заметка не заполнена ни в одной из
2243 операций, так что удалять нечего.

**assets.is_personal_use** — квартира, в которой живут, и машина, на
которой ездят. Заводить их стоит: без них продажа выглядит доходом из
ниоткуда. Но показывать человеку «капитал шесть миллионов», из которых
5,8 — жильё, которое он не продаст, значит показывать число, на которое
нельзя опереться ни в одном решении.

Revision ID: 0005_optional_description
Revises: 0004_goal_accounts
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_optional_description"
down_revision = "0004_goal_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("transactions", "description", existing_type=sa.String(length=255), nullable=True)
    op.drop_column("transactions", "notes")
    op.add_column(
        "assets",
        sa.Column("is_personal_use", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("assets", "is_personal_use")
    op.add_column("transactions", sa.Column("notes", sa.Text(), nullable=True))
    # Пустое описание при откате превращается в прочерк: колонка снова
    # становится обязательной, и строки без описания иначе не вернуть.
    op.execute("UPDATE transactions SET description = '—' WHERE description IS NULL")
    op.alter_column("transactions", "description", existing_type=sa.String(length=255), nullable=False)
