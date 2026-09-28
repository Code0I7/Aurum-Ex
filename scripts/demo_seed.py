"""Демонстрационные данные: выдуманная, но правдоподобная установка.

Нужны для скриншотов и для того, чтобы приложение можно было посмотреть, не
занося свою жизнь руками. Данные полностью вымышленные: ни одного числа,
имени или даты из чьей-либо настоящей истории здесь нет.

Запускается внутри контейнера backend на ПУСТОЙ базе:

    docker compose exec backend python /app/../scripts/demo_seed.py ru

Аргумент — язык подписей (ru или en). Он меняет то, что человек вводит сам:
названия счетов, имена людей, описания операций, названия целей. Категории
берутся из засева установки: они переводятся сами, и один и тот же набор
данных читается на обоих языках.

Суммы масштабируются под валюту: рублёвая зарплата в 85 000 и долларовая в
2 400 выглядят одинаково обычными, а одно и то же число — нет.
"""
import asyncio
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.account import Account, Bank
from app.models.category import Category
from app.models.counterparty import Counterparty
from app.models.currency import ExchangeRate
from app.models.enums import (
    AccountKind,
    AccountNature,
    AssetClass,
    CapitalRole,
    GoalStatus,
    InvestmentKind,
    ParticipantKind,
    PlanFrequency,
    RecurringFrequency,
    RiskLevel,
    SettlementKind,
    TradeSide,
    TransactionType,
)
from app.models.asset import Asset, AssetValuation
from app.models.investment import InvestmentHolding, InvestmentPortfolio, InvestmentTrade
from app.models.participant import Participant
from app.models.plan import Plan, PlanPeriod
from app.models.product import Product
from app.models.recurring import RecurringTransaction
from app.models.store import Store
from app.models.unit import Unit
from app.models.goal import Goal, GoalContribution
from app.models.budget import Budget
from app.models.credit import CreditTerms
from app.models.settings import AppSettings
from app.models.transaction import Transaction, TransactionItem
from app.models.work_period import WorkPeriod

# День, относительно которого строится история. Фиксированный, а не
# сегодняшний: скриншоты должны получаться одинаковыми при любом повторе.
TODAY = date(2026, 9, 27)
START = date(2026, 1, 1)

LABELS = {
    "ru": {
        "currency": "RUB",
        "scale": 1,
        "accounts": ["Основная карта", "Кредитная карта", "Наличные", "Накопительный"],
        "banks": ["Первый банк", "Второй банк"],
        "people": ["Алексей", "Катя"],
        "goals": [
            ("Ноутбук для работы", 90_000, date(2026, 6, 1), date(2027, 2, 1), None),
            ("Отпуск у моря", 120_000, date(2026, 3, 1), date(2027, 6, 1), None),
            ("Зимняя резина", 40_000, date(2025, 12, 1), None, date(2026, 4, 12)),
        ],
        "spending": [
            ("Продукты на неделю", "Groceries", 1200, 4200),
            ("Кофе и завтрак", "Dining Out", 250, 700),
            ("Проездной", "Transportation", 60, 120),
            ("Подписка на музыку", "Subscriptions", 199, 299),
            ("Аптека", "Health & Fitness", 300, 1500),
            ("Одежда", "Shopping", 1500, 6000),
            ("Кино с друзьями", "Entertainment", 400, 1200),
            ("Коммунальные платежи", "Housing & Utilities", 4500, 7000),
        ],
        "salary": "Зарплата",
        "freelance": "Подработка",
        "transfer_cash": "Снял наличные",
        "transfer_savings": "Отложил на накопительный",
        "credit_payment": "Погашение кредитки",
        "gift_out": "Одолжил до зарплаты",
        "gift_in": "Вернули долг",
        "transit_in": "Прислали на продукты",
        # Участники — на кого записана операция. Питомец здесь же: корм для
        # кота — это и «Продукты», и «на Барсика».
        "participants": [("Алексей", ParticipantKind.PERSON), ("Катя", ParticipantKind.PERSON), ("Барсик", ParticipantKind.PET)],
        "stores": [("Магазин у дома", "продуктовые"), ("Гипермаркет", "продуктовые"), ("Рынок", "продуктовые")],
        # (товар, единица, базовая цена, шаг подорожания за месяц)
        "products": [
            ("Молоко 3,2%", "л", 92, 1.5),
            ("Хлеб ржаной", "шт", 58, 0.8),
            ("Сыр твёрдый", "кг", 780, 9),
            ("Кофе в зёрнах", "кг", 1980, 14),
            ("Яйца, 10 шт", "шт", 135, 1.2),
            ("Бананы", "кг", 145, 1),
            ("Масло сливочное", "кг", 1180, 12),
        ],
        # Инвестиции: цены и количества выдуманы целиком, тикеры тоже.
        "portfolio": "Брокерский счёт",
        "holdings": [
            ("Индексный фонд", "IDX", InvestmentKind.FUND, RiskLevel.MEDIUM,
             [(date(2026, 2, 10), 20, 3900), (date(2026, 5, 15), 10, 4200)], 4450),
            ("Облигации", "BND", InvestmentKind.BOND, RiskLevel.LOW,
             [(date(2026, 3, 5), 10, 3200)], 3300),
            ("Золото", "GLD", InvestmentKind.METAL, RiskLevel.MEDIUM,
             [(date(2026, 1, 20), 2, 7000)], 8200),
            ("Акции банка", "BNK", InvestmentKind.STOCK, RiskLevel.HIGH,
             [(date(2026, 6, 2), 10, 1400)], 1270),
        ],
        # Имущество: в капитал входит, но помечено личным — машина, на
        # которой ездят, не деньги.
        "asset": ("Автомобиль", [(date(2026, 1, 1), 620_000), (date(2026, 9, 1), 580_000)]),
        # Планы: сколько денег ожидается по статье, а не сколько потрачено.
        "plans": [
            ("Salary", PlanFrequency.MONTH, 85_000, "Две части: 10-го и 25-го"),
            ("Freelance", PlanFrequency.MONTH, 8_000, "Подработка, в среднем"),
            ("Housing & Utilities", PlanFrequency.MONTH, 24_000, "Квартплата и свет"),
            ("Dining Out", PlanFrequency.DAY, 350, "Обед на работе"),
            ("Subscriptions", PlanFrequency.MONTH, 900, "Музыка и облако"),
        ],
        "recurring": [
            ("Подписка на музыку", "Subscriptions", 199, RecurringFrequency.MONTHLY, 23),
            ("Абонемент в зал", "Health & Fitness", 2_200, RecurringFrequency.MONTHLY, 3),
            ("Страховка на машину", "Transportation", 9_800, RecurringFrequency.YEARLY, 14),
        ],
    },
    "en": {
        "currency": "USD",
        "scale": Decimal("0.03"),
        "accounts": ["Everyday card", "Credit card", "Cash", "Savings"],
        "banks": ["First Bank", "Second Bank"],
        "people": ["Alex", "Kate"],
        "goals": [
            ("Laptop for work", 90_000, date(2026, 6, 1), date(2027, 2, 1), None),
            ("Seaside holiday", 120_000, date(2026, 3, 1), date(2027, 6, 1), None),
            ("Winter tyres", 40_000, date(2025, 12, 1), None, date(2026, 4, 12)),
        ],
        "spending": [
            ("Weekly groceries", "Groceries", 1200, 4200),
            ("Coffee and breakfast", "Dining Out", 250, 700),
            ("Transit pass", "Transportation", 60, 120),
            ("Music subscription", "Subscriptions", 199, 299),
            ("Pharmacy", "Health & Fitness", 300, 1500),
            ("Clothes", "Shopping", 1500, 6000),
            ("Cinema with friends", "Entertainment", 400, 1200),
            ("Utilities", "Housing & Utilities", 4500, 7000),
        ],
        "salary": "Salary",
        "freelance": "Freelance",
        "transfer_cash": "Cash withdrawal",
        "transfer_savings": "Moved to savings",
        "credit_payment": "Credit card payment",
        "gift_out": "Lent until payday",
        "gift_in": "Debt returned",
        "transit_in": "Sent for groceries",
        "participants": [("Alex", ParticipantKind.PERSON), ("Kate", ParticipantKind.PERSON), ("Barney", ParticipantKind.PET)],
        "stores": [("Corner shop", "groceries"), ("Hypermarket", "groceries"), ("Farmers market", "groceries")],
        "products": [
            ("Milk 3.2%", "л", 2.8, 0.05),
            ("Rye bread", "шт", 1.7, 0.02),
            ("Hard cheese", "кг", 23, 0.3),
            ("Coffee beans", "кг", 59, 0.4),
            ("Eggs, 10", "шт", 4.1, 0.03),
            ("Bananas", "кг", 4.4, 0.02),
            ("Butter", "кг", 35, 0.35),
        ],
        "portfolio": "Brokerage",
        "holdings": [
            ("Index fund", "IDX", InvestmentKind.FUND, RiskLevel.MEDIUM,
             [(date(2026, 2, 10), 20, 118), (date(2026, 5, 15), 10, 127)], 135),
            ("Treasury bonds", "BND", InvestmentKind.BOND, RiskLevel.LOW,
             [(date(2026, 3, 5), 10, 97)], 100),
            ("Gold", "GLD", InvestmentKind.METAL, RiskLevel.MEDIUM,
             [(date(2026, 1, 20), 2, 212)], 248),
            ("Bank shares", "BNK", InvestmentKind.STOCK, RiskLevel.HIGH,
             [(date(2026, 6, 2), 10, 42)], 38),
        ],
        "asset": ("Car", [(date(2026, 1, 1), 18_600), (date(2026, 9, 1), 17_400)]),
        "plans": [
            ("Salary", PlanFrequency.MONTH, 2_550, "Two parts: the 10th and the 25th"),
            ("Freelance", PlanFrequency.MONTH, 240, "Side work, on average"),
            ("Housing & Utilities", PlanFrequency.MONTH, 720, "Rent and power"),
            ("Dining Out", PlanFrequency.DAY, 11, "Lunch at work"),
            ("Subscriptions", PlanFrequency.MONTH, 27, "Music and cloud"),
        ],
        "recurring": [
            ("Music subscription", "Subscriptions", 6, RecurringFrequency.MONTHLY, 23),
            ("Gym membership", "Health & Fitness", 66, RecurringFrequency.MONTHLY, 3),
            ("Car insurance", "Transportation", 294, RecurringFrequency.YEARLY, 14),
        ],
    },
}


def money(value, scale) -> Decimal:
    """Сумма в валюте установки: рублёвые числа делятся на масштаб и
    округляются до целого, чтобы доллары не выглядели пересчётом."""
    return (Decimal(value) * Decimal(scale)).quantize(Decimal("1")) if scale != 1 else Decimal(value)


async def main(language: str) -> None:
    labels = LABELS[language]
    scale = labels["scale"]
    rng = random.Random(20260927)

    async with AsyncSessionLocal() as session:
        settings = await session.get(AppSettings, 1)
        if settings is not None:
            settings.currency = labels["currency"]

        categories = {
            row.name: row
            for row in (await session.execute(select(Category))).scalars().all()
        }

        # --- счета ---------------------------------------------------------
        existing = (await session.execute(select(Account))).scalars().all()
        for account in existing:
            await session.delete(account)
        await session.flush()

        # Два банка: карта и накопительный в одном, кредитка в другом —
        # ровно тот случай, ради которого группировка по банку и сделана.
        banks = [
            Bank(name=name, color=color, sort_order=order)
            for order, (name, color) in enumerate(zip(labels["banks"], ("#2a78d6", "#eda100")))
        ]
        session.add_all(banks)
        await session.flush()

        card, credit, cash, savings = (
            Account(
                name=labels["accounts"][0],
                kind=AccountKind.CHECKING,
                nature=AccountNature.ASSET,
                currency=labels["currency"],
                bank_id=banks[0].id,
                opening_balance=money(42_000, scale),
                opening_date=date(2025, 12, 1),
            ),
            Account(
                name=labels["accounts"][1],
                kind=AccountKind.CREDIT_CARD,
                nature=AccountNature.LIABILITY,
                currency=labels["currency"],
                bank_id=banks[1].id,
            ),
            Account(
                name=labels["accounts"][2],
                kind=AccountKind.CASH,
                nature=AccountNature.ASSET,
                currency=labels["currency"],
            ),
            Account(
                name=labels["accounts"][3],
                kind=AccountKind.SAVINGS,
                nature=AccountNature.ASSET,
                currency=labels["currency"],
                bank_id=banks[0].id,
            ),
        )
        session.add_all([card, credit, cash, savings])
        await session.flush()

        people = [Counterparty(name=name) for name in labels["people"]]
        session.add_all(people)

        # Участники и контрагенты — разные справочники, и путать их нельзя:
        # участник это «на кого потрачено», контрагент — «с кем считаемся».
        participants = [Participant(name=name, kind=kind) for name, kind in labels["participants"]]
        session.add_all(participants)

        stores = [Store(name=name, group_name=group) for name, group in labels["stores"]]
        session.add_all(stores)
        await session.flush()

        # Единицы засеяны установкой по-русски; в английской демонстрации их
        # видно в позициях чека, поэтому переименовываются. На настоящей
        # установке это правит человек — справочник для того и заведён.
        if language == "en":
            renames = {"кг": "kg", "г": "g", "л": "l", "мл": "ml", "шт": "pcs", "упак": "pack", "м": "m", "оплата": "service"}
            for unit in (await session.execute(select(Unit))).scalars().all():
                if unit.name in renames:
                    unit.name = renames[unit.name]
            await session.flush()

        units = {row.name: row for row in (await session.execute(select(Unit))).scalars().all()}
        unit_alias = {"кг": "kg", "л": "l", "шт": "pcs"} if language == "en" else {}
        products = []
        for name, unit_name, base_price, monthly_step in labels["products"]:
            unit = units[unit_alias.get(unit_name, unit_name)]
            product = Product(name=name, unit_id=unit.id)
            products.append((product, unit, Decimal(str(base_price)), Decimal(str(monthly_step))))
            session.add(product)
        await session.flush()

        # --- операции ------------------------------------------------------
        def add(
            account,
            kind: TransactionType,
            amount,
            when: date,
            description: str,
            category: str | None = None,
            **extra,
        ) -> Transaction:
            value = money(amount, scale)
            row = Transaction(
                account_id=account.id,
                type=kind,
                amount=value,
                currency=labels["currency"],
                exchange_rate=Decimal("1"),
                amount_base=value,
                date=when,
                description=description,
                category_id=categories[category].id if category else None,
                **extra,
            )
            session.add(row)
            # Возвращается ради позиций чека: их вешают на уже созданную
            # операцию, а остальные вызовы результат просто не смотрят.
            return row

        day = START
        while day <= TODAY:
            # Зарплата двумя частями, как её и платят.
            if day.day == 10:
                add(card, TransactionType.INCOME, 38_000, day, labels["salary"], "Salary")
            if day.day == 25:
                add(card, TransactionType.INCOME, 47_000, day, labels["salary"], "Salary")
            if day.day == 18 and day.month % 2 == 0:
                add(card, TransactionType.INCOME, rng.randrange(9_000, 24_000), day, labels["freelance"], "Freelance")

            # Траты: несколько в неделю, разных видов.
            for description, category, low, high in labels["spending"]:
                if rng.random() > 0.12:
                    continue
                account = credit if rng.random() < 0.2 else card
                # Участник — не у всякой траты: коммуналка и проездной ничьи.
                owner = None
                if category in ("Groceries", "Dining Out", "Shopping", "Health & Fitness"):
                    owner = rng.choice(participants).id
                row = add(
                    account,
                    TransactionType.EXPENSE,
                    rng.randrange(low, high),
                    day,
                    description,
                    category,
                    participant_id=owner,
                    store_id=rng.choice(stores).id if category == "Groceries" else None,
                )
                if category != "Groceries":
                    continue
                # Чек расписан по позициям: из них и складывается кривая цены
                # товара. Цена ползёт вверх помесячно — ровно то, ради чего
                # цены и записывают.
                months = (day.year - START.year) * 12 + day.month - START.month
                await session.flush()
                for position, (product, unit, base_price, step) in enumerate(rng.sample(products, 2)):
                    # Цены товаров заданы в валюте языка сразу, без общего
                    # масштаба: доллар за литр молока — не рубль, делённый на 33.
                    price = base_price + step * months
                    quantity = Decimal(rng.choice(["0.2", "0.3", "0.5", "1"]))
                    session.add(
                        TransactionItem(
                            transaction_id=row.id,
                            product_id=product.id,
                            name=product.name,
                            quantity=quantity,
                            unit_id=unit.id,
                            price=price.quantize(Decimal("0.01")),
                            amount=(price * quantity).quantize(Decimal("0.01")),
                            position=position,
                        )
                    )

            if day.day == 5:
                add(card, TransactionType.TRANSFER, 8_000, day, labels["transfer_cash"], transfer_account_id=cash.id)
            if day.day == 26:
                add(card, TransactionType.TRANSFER, 15_000, day, labels["transfer_savings"], transfer_account_id=savings.id)
            if day.day == 20:
                add(card, TransactionType.TRANSFER, 8_000, day, labels["credit_payment"], transfer_account_id=credit.id)

            # Расчёты с людьми: заём, возврат и транзит.
            if day.day == 14 and day.month % 3 == 0:
                add(
                    card,
                    TransactionType.EXTERNAL_OUT,
                    5_000,
                    day,
                    labels["gift_out"],
                    None,
                    counterparty_id=people[0].id,
                    settlement_kind=SettlementKind.LOAN_OUT,
                )
            if day.day == 28 and day.month % 3 == 0:
                add(
                    card,
                    TransactionType.EXTERNAL_IN,
                    5_000,
                    day,
                    labels["gift_in"],
                    None,
                    counterparty_id=people[0].id,
                    settlement_kind=SettlementKind.REPAYMENT,
                )
            if day.day == 8:
                add(
                    card,
                    TransactionType.EXTERNAL_IN,
                    3_000,
                    day,
                    labels["transit_in"],
                    "Groceries",
                    counterparty_id=people[1].id,
                    transit_party_id=people[1].id,
                    settlement_kind=SettlementKind.TRANSIT,
                )
            day += timedelta(days=1)

        # --- цели ----------------------------------------------------------
        for name, target, started, planned, closed in labels["goals"]:
            goal = Goal(
                name=name,
                target_amount=money(target, scale),
                started_on=started,
                planned_on=planned,
                closed_at=closed,
                status=GoalStatus.ACHIEVED if closed else GoalStatus.ACTIVE,
                account_id=savings.id,
            )
            session.add(goal)
            await session.flush()
            # Взносы раз в месяц от начала накопления: у завершённой цели —
            # до самого дня сбора, у активной — до сегодня.
            end = closed or TODAY
            steps = 0
            probe = started
            while probe < end:
                steps += 1
                probe += timedelta(days=30)
            # У активной цели откладывается ровно столько, сколько уходит на
            # накопительный: пятнадцать тысяч в месяц на три цели. Иначе
            # «отложено» выходит больше остатка и счёт показывает «доступно 0».
            # Завершённая цель добирается точно до суммы — достигнутая цель с
            # недобранным сбором в списке выглядит ошибкой.
            if closed:
                total = money(target, scale)
                step = (total / steps).quantize(Decimal("1"))
                amounts = [step] * (steps - 1) + [total - step * (steps - 1)]
            else:
                amounts = [money(5_000, scale)] * steps
            when = started
            for amount in amounts:
                session.add(
                    GoalContribution(
                        goal_id=goal.id,
                        amount=amount,
                        date=when,
                        account_id=savings.id,
                    )
                )
                when += timedelta(days=30)

        # --- условия по кредитке ---------------------------------------------
        # Без условий вкладка «Долги» показывает только расчёты с людьми, а
        # половина её смысла — беспроцентный период и дата платежа.
        session.add(
            CreditTerms(
                account_id=credit.id,
                annual_rate_percent=Decimal("24.9"),
                credit_limit=money(150_000, scale),
                grace_days=120,
                payment_day=15,
                minimum_payment=money(3_000, scale),
                opened_on=date(2025, 11, 20),
            )
        )

        # --- инвестиции ------------------------------------------------------
        # Цена последняя известная, а не котировка: внешний источник в
        # демонстрации не опрашивается, и придумывать ему ответ нечестно.
        portfolio = InvestmentPortfolio(name=labels["portfolio"], color="#2a78d6")
        session.add(portfolio)
        await session.flush()
        priced_at = datetime(TODAY.year, TODAY.month, TODAY.day, 18, 0, tzinfo=timezone.utc)
        for name, ticker, kind, risk, trades, last_price in labels["holdings"]:
            holding = InvestmentHolding(
                portfolio_id=portfolio.id,
                name=name,
                ticker=ticker,
                kind=kind,
                currency=labels["currency"],
                risk_level=risk,
                last_price=Decimal(str(last_price)),
                last_price_at=priced_at,
            )
            session.add(holding)
            await session.flush()
            for when, quantity, price in trades:
                session.add(
                    InvestmentTrade(
                        holding_id=holding.id,
                        side=TradeSide.BUY,
                        quantity=Decimal(quantity),
                        price_per_unit=Decimal(str(price)),
                        fee=Decimal("0"),
                        trade_date=when,
                    )
                )

        # --- имущество -------------------------------------------------------
        name, valuations = labels["asset"]
        asset = Asset(
            name=name,
            asset_class=AssetClass.VEHICLES,
            currency=labels["currency"],
            is_personal_use=True,
            capital_role=CapitalRole.DRAIN,
            risk_level=RiskLevel.MEDIUM,
        )
        session.add(asset)
        await session.flush()
        for when, value in valuations:
            session.add(AssetValuation(asset_id=asset.id, value=Decimal(value), as_of_date=when))

        # --- планы -----------------------------------------------------------
        for category, frequency, amount, note in labels["plans"]:
            plan = Plan(
                category_id=categories[category].id,
                kind=frequency,
                currency=labels["currency"],
                # Обед на работе бывает только в рабочие дни: считать его по
                # календарным завысило бы план в полтора раза.
                workdays_only=frequency == PlanFrequency.DAY,
                note=note,
            )
            session.add(plan)
            await session.flush()
            session.add(PlanPeriod(plan_id=plan.id, amount=Decimal(amount), valid_from=START))

        # --- регулярные платежи ------------------------------------------------
        for description, category, amount, frequency, day_of_month in labels["recurring"]:
            session.add(
                RecurringTransaction(
                    account_id=card.id,
                    category_id=categories[category].id,
                    type=TransactionType.EXPENSE,
                    amount=Decimal(amount),
                    description=description,
                    frequency=frequency,
                    anchor_date=date(2026, 1, day_of_month),
                )
            )

        for name in ("Groceries", "Dining Out", "Salary"):
            categories[name].is_watched = True

        # --- бюджеты ---------------------------------------------------------
        for category, limit in (("Groceries", 18_000), ("Dining Out", 6_000), ("Entertainment", 4_000)):
            session.add(Budget(category_id=categories[category].id, monthly_limit=money(limit, scale)))

        # --- отработанное время (заработок в час) ----------------------------
        for month in range(1, TODAY.month + 1):
            session.add(WorkPeriod(year=2026, month=month, hours=Decimal("152")))

        # --- курсы валют -----------------------------------------------------
        # Небольшая синтетическая история: чтобы блок «Курсы» и график по
        # валюте было на чём показать. К настоящим котировкам отношения не
        # имеет.
        base = {"USD": Decimal("84"), "EUR": Decimal("96"), "CNY": Decimal("12.5")}
        if labels["currency"] == "RUB":
            for offset in range(60):
                when = TODAY - timedelta(days=offset)
                for code, value in base.items():
                    drift = Decimal(rng.randrange(-150, 150)) / Decimal("100")
                    session.add(
                        ExchangeRate(
                            code=code,
                            rate_date=when,
                            rate=(value + drift).quantize(Decimal("0.0001")),
                            published_for=when,
                        )
                    )

        await session.commit()

        total = len((await session.execute(select(Transaction))).scalars().all())
        items = len((await session.execute(select(TransactionItem))).scalars().all())
        print(
            "готово: операций %d (позиций в чеках %d), счетов 4, целей %d, бумаг %d"
            % (total, items, len(labels["goals"]), len(labels["holdings"]))
        )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ru"))
