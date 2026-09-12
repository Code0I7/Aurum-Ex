"""aurum-ex: доллар, евро и юань в списке наблюдения

Справочник валют стал списком наблюдения: строка в нём означает «за курсом
этой валюты я слежу». У рублёвой установки это доллар, евро и юань — их
курс интересен и тому, у кого нет ни одного валютного счёта.

Только здесь, разово. В заполнении при старте такой список держать нельзя:
валюта, убранная человеком, возвращалась бы при каждом перезапуске.

Названия и символы не заполняются намеренно: подписи валют живут в
интерфейсе, сразу на двух языках, и вторая их копия в базе разошлась бы с
первой при первой же правке.

Revision ID: 0019_watchlist_defaults
Revises: 0018_amount_base_nullable
"""
from alembic import op

revision = "0019_watchlist_defaults"
down_revision = "0018_amount_base_nullable"
branch_labels = None
depends_on = None

WATCHED = ("USD", "EUR", "CNY")


def upgrade() -> None:
    for code in WATCHED:
        # ON CONFLICT: валюта могла появиться сама — от счёта в ней или от
        # операции. Тогда она уже в списке, и трогать её нечего.
        op.execute(
            "INSERT INTO currencies (code, cbr_nominal, is_active, created_at, updated_at) "
            f"VALUES ('{code}', 1, true, now(), now()) ON CONFLICT (code) DO NOTHING"
        )


def downgrade() -> None:
    # Убираются только те, которыми никто не пользуется: валюта счёта или
    # операции нужна расчётам, и удалить её отсюда значило бы перестать
    # загружать её курс.
    codes = ", ".join(f"'{code}'" for code in WATCHED)
    op.execute(
        f"DELETE FROM currencies WHERE code IN ({codes}) "
        "AND code NOT IN (SELECT DISTINCT currency FROM accounts) "
        "AND code NOT IN (SELECT DISTINCT currency FROM transactions)"
    )
