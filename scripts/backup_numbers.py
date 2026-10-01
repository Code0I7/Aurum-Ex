"""Контрольные числа установки: с чем сверять копию после восстановления.

Считает не только строки. Копия, в которой все строки на месте, а суммы
разъехались, — это не копия, и заметить такое можно только сверкой самих
чисел: количество строк переживает и потерянную дробную часть, и съехавший
на день период, и перепутанные местами поля.

Запускается внутри контейнера backend, читает базу и ничего в неё не пишет:

    docker compose exec backend python /app/scripts/backup_numbers.py

Используется scripts/restore-drill.sh по обе стороны проверки — до снятия
копии и после восстановления.
"""
import asyncio
import json
import sys

from sqlalchemy import text

from app.db.session import AsyncSessionLocal

# Все таблицы с пользовательскими данными. Пустые тоже перечислены: ноль до
# и ноль после — такой же результат, как совпавшие тысячи, а вот ноль после
# непустого «до» — потерянный раздел копии.
COUNTS = [
    "accounts", "banks", "categories", "tags", "transactions", "transaction_splits",
    "transaction_items", "transaction_counterparty_splits", "transfer_match_dismissals",
    "assets", "asset_valuations", "crypto_portfolios", "crypto_holdings",
    "crypto_transactions", "goals", "goal_contributions", "budgets", "plans",
    "plan_periods", "work_periods", "products", "stores", "counterparties",
    "participants", "units", "currencies", "exchange_rates", "credit_terms",
    "credit_rates", "recurring_transactions", "investment_portfolios",
    "investment_holdings", "investment_trades", "dashboard_widgets",
]

# Числа, которые обязаны совпасть до копейки, и границы периода: съехавший на
# день диапазон — та же потеря, только незаметнее.
SUMS = {
    "операции, сумма": "select coalesce(sum(amount), 0) from transactions",
    "операции, в базовой валюте": "select coalesce(sum(amount_base), 0) from transactions",
    "доли по категориям": "select coalesce(sum(amount), 0) from transaction_splits",
    "доли по людям": "select coalesce(sum(amount), 0) from transaction_counterparty_splits",
    "позиции чеков": "select coalesce(sum(amount), 0) from transaction_items",
    "оценки имущества": "select coalesce(sum(value), 0) from asset_valuations",
    "начальные остатки счетов": "select coalesce(sum(opening_balance), 0) from accounts",
    "взносы в цели": "select coalesce(sum(amount), 0) from goal_contributions",
    "цели, сумма": "select coalesce(sum(target_amount), 0) from goals",
    "суммы планов": "select coalesce(sum(amount), 0) from plan_periods",
    "отработанные часы": "select coalesce(sum(hours), 0) from work_periods",
    "курсы валют": "select coalesce(sum(rate), 0) from exchange_rates",
    "сделки по бумагам": "select coalesce(sum(quantity * price_per_unit), 0) from investment_trades",
    "операций не в учёте": "select count(*) from transactions where is_excluded",
    "первая операция": "select coalesce(min(date)::text, '-') from transactions",
    "последняя операция": "select coalesce(max(date)::text, '-') from transactions",
    "валюта установки": "select currency from app_settings limit 1",
    "считать долг тратой": "select lending_is_spending::text from app_settings limit 1",
}


async def collect() -> dict:
    out: dict = {"counts": {}, "sums": {}}
    async with AsyncSessionLocal() as session:
        for table in COUNTS:
            value = (await session.execute(text("select count(*) from " + table))).scalar_one()
            out["counts"][table] = int(value)
        for label, query in SUMS.items():
            value = (await session.execute(text(query))).scalar_one()
            out["sums"][label] = "-" if value is None else str(value)
    return out


def main() -> None:
    numbers = asyncio.run(collect())
    path = sys.argv[1] if len(sys.argv) > 1 else None
    text_out = json.dumps(numbers, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text_out + "\n")
    print(text_out)


main()
