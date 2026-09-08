"""aurum-ex: счёт у взноса в цель и счёт по умолчанию

Две добавочные колонки.

**goal_contributions.account_id** — с какого счёта отложены деньги. Раньше
счёт был у самой цели, один на всё накопление, и «три тысячи наличными,
две безналом» этим не выражалось. Резерв должен вестись по каждому счёту
отдельно, иначе вернуть с наличных можно было бы больше, чем с них
откладывали.

Существующие взносы заполняются счётом своей цели: это ровно то, что они
и означали до сих пор, просто сказанное явно. Ни одно уже записанное
значение при этом не меняется.

**app_settings.default_account_id** — счёт, который подставляется в новую
операцию. Основная карта у человека одна, и выбирать её каждый раз из
списка — лишний шаг на самом частом действии.

Revision ID: 0004_goal_accounts
Revises: 0003_category_watchlist
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_goal_accounts"
down_revision = "0003_category_watchlist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("goal_contributions", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_goal_contributions_account_id",
        "goal_contributions",
        "accounts",
        ["account_id"],
        ["id"],
        # SET NULL, как и везде: удаление счёта не должно стирать историю
        # накопления. Взнос останется, просто перестанет что-либо резервировать.
        ondelete="SET NULL",
    )
    # Заполнение из счёта цели. Строки, у которых счёта нет и у цели тоже,
    # остаются пустыми — они ничего не резервировали и раньше.
    op.execute(
        """
        UPDATE goal_contributions AS gc
           SET account_id = g.account_id
        FROM goals AS g
        WHERE g.id = gc.goal_id AND g.account_id IS NOT NULL
        """
    )

    op.add_column("app_settings", sa.Column("default_account_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_app_settings_default_account_id",
        "app_settings",
        "accounts",
        ["default_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_app_settings_default_account_id", "app_settings", type_="foreignkey")
    op.drop_column("app_settings", "default_account_id")
    op.drop_constraint("fk_goal_contributions_account_id", "goal_contributions", type_="foreignkey")
    op.drop_column("goal_contributions", "account_id")
