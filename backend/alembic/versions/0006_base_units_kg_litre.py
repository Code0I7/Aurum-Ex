"""aurum-ex: базовая мера — килограмм и литр, а не грамм и миллилитр

Цена за базовую единицу выходила нечитаемой: «0,074 за миллилитр» —
арифметически верно и бесполезно, потому что в магазине сравнивают рубли за
литр. Килограмм и литр — то, чем люди меряют на самом деле.

Меняется только справочник единиц: коэффициенты и признак базовой. Цена за
базовую меру нигде не хранится — она считается на лету из количества,
суммы и коэффициента, — поэтому ни одна записанная покупка не меняется.
Меняется лишь то, в каких единицах она показывается: было 0,074 ₽/мл,
станет 74 ₽/л. Само число покупки, её сумма и количество остаются теми же.

Обновляются только строки, оставшиеся в засеянном виде: если коэффициент
уже правили руками, он не трогается — своя мера принадлежит человеку.

Revision ID: 0006_base_units
Revises: 0005_optional_description
"""
from alembic import op

revision = "0006_base_units"
down_revision = "0005_optional_description"
branch_labels = None
depends_on = None


# (вид, имя новой базовой, имя прежней базовой, коэффициент прежней)
SWAPS = [
    ("MASS", "кг", "г", "0.001"),
    ("VOLUME", "л", "мл", "0.001"),
]


def upgrade() -> None:
    for kind, new_base, old_base, small_factor in SWAPS:
        # Только нетронутая пара: новая базовая всё ещё «тысяча прежних», а
        # прежняя всё ещё помечена базовой. Иначе человек уже перестроил
        # меры под себя, и лезть туда нельзя.
        op.execute(
            f"""
            UPDATE units SET factor = 1, is_base = true
            WHERE kind = '{kind}' AND name = '{new_base}' AND factor = 1000 AND is_base = false
              AND EXISTS (
                SELECT 1 FROM units u2
                WHERE u2.kind = '{kind}' AND u2.name = '{old_base}' AND u2.factor = 1 AND u2.is_base = true
              )
            """
        )
        op.execute(
            f"""
            UPDATE units SET factor = {small_factor}, is_base = false
            WHERE kind = '{kind}' AND name = '{old_base}' AND factor = 1 AND is_base = true
              AND EXISTS (
                SELECT 1 FROM units u2
                WHERE u2.kind = '{kind}' AND u2.name = '{new_base}' AND u2.factor = 1 AND u2.is_base = true
              )
            """
        )


def downgrade() -> None:
    for kind, new_base, old_base, small_factor in SWAPS:
        op.execute(
            f"UPDATE units SET factor = 1, is_base = true "
            f"WHERE kind = '{kind}' AND name = '{old_base}' AND factor = {small_factor}"
        )
        op.execute(
            f"UPDATE units SET factor = 1000, is_base = false "
            f"WHERE kind = '{kind}' AND name = '{new_base}' AND factor = 1"
        )
