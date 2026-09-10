"""aurum-ex: индексы под список операций и состав чека

У `transactions` было ровно два индекса — первичный ключ и уникальность
uuid. Ни одного по колонкам, по которым список читается: он всегда
сортируется по дате и порядку внутри дня, а фильтруется по счёту и
категории. Postgres честно читал таблицу целиком и сортировал в памяти.

На двух с половиной тысячах строк это 2 мс, и заметить нечего. Разница
появляется дальше: на 50 000 строк тот же запрос — 7,9 мс без индекса и
0,23 мс с ним, потому что вместо «прочитать всё и отсортировать» получается
«взять пятьдесят подряд идущих записей». Это не ускорение на треть, это
смена порядка роста, и добавлять индекс дешевле сейчас, чем когда список
начнёт тормозить.

Отдельная история — дочерние таблицы. Внешние ключи Postgres сам не
индексирует, поэтому подгрузка сплитов и позиций чека к странице списка
(`WHERE transaction_id IN (...)`) читала обе таблицы целиком на каждой
странице. Пока позиций чека три десятка, это ничто; они и заведены, чтобы
их стало много.

Ничего не меняется в поведении: индексы видны только планировщику.

Revision ID: 0008_transaction_indexes
Revises: 0007_show_cents
"""
from alembic import op

revision = "0008_transaction_indexes"
down_revision = "0007_show_cents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Порядок колонок повторяет ORDER BY списка: дата, затем порядок внутри
    # дня. Индекс обычный, по возрастанию: список читается с последнего дня
    # вверх, но Postgres проходит индекс в обратную сторону сам, когда все
    # колонки перевёрнуты одинаково.
    op.create_index("ix_transactions_date_day_order", "transactions", ["date", "day_order"])
    # Счёт: и как фильтр списка, и как обе стороны перевода при подсчёте
    # остатка. Вторая колонка — та самая вторая сторона.
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_index("ix_transactions_transfer_account_id", "transactions", ["transfer_account_id"])
    # Категория: фильтр отчётов и списка. Теперь по ветке, то есть IN
    # (...) по списку из десятков значений — как раз то, что индекс умеет.
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])
    # Дочерние таблицы — под подгрузку к странице списка.
    op.create_index("ix_transaction_splits_transaction_id", "transaction_splits", ["transaction_id"])
    op.create_index("ix_transaction_items_transaction_id", "transaction_items", ["transaction_id"])
    # Кривая цены: все позиции одного товара за всё время.
    op.create_index("ix_transaction_items_product_id", "transaction_items", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_transaction_items_product_id", table_name="transaction_items")
    op.drop_index("ix_transaction_items_transaction_id", table_name="transaction_items")
    op.drop_index("ix_transaction_splits_transaction_id", table_name="transaction_splits")
    op.drop_index("ix_transactions_category_id", table_name="transactions")
    op.drop_index("ix_transactions_transfer_account_id", table_name="transactions")
    op.drop_index("ix_transactions_account_id", table_name="transactions")
    op.drop_index("ix_transactions_date_day_order", table_name="transactions")
