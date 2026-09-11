"""aurum-ex: у контрагента есть полка

То же, что у магазинов, и по той же причине: список копится и в нём
вперемешку лежат «Близкие», коллеги, случайные знакомые и организации.
Найти нужное можно, только зная имя целиком.

Полка задаётся человеком и живёт только на странице справочников: ни в
отчёты, ни в подстановку не идёт. Свободная строка, а не список: набор
полок у каждого свой.

Колонка называется group_name — `group` в SQL ключевое слово.

Revision ID: 0015_counterparty_group
Revises: 0014_transit_party
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_counterparty_group"
down_revision = "0014_transit_party"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("counterparties", sa.Column("group_name", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("counterparties", "group_name")
