"""Shared enum types used by the ORM models and API schemas."""
import enum


class AccountKind(str, enum.Enum):
    """What kind of place the money sits in. Renamed from the original
    `AccountType` — "type" read as "kind of record" and kept getting
    confused with an account in the login sense. Deliberately says nothing
    about whether the balance counts as an asset or a debt: that is a
    separate axis, see AccountNature below, because a credit card and a
    loan are different kinds sharing one nature, while a checking account
    and cash are different kinds sharing the other."""

    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    CASH = "cash"
    INVESTMENT = "investment"
    # Кошелёк или счёт на бирже. Отдельно от инвестиционного: у него другая
    # природа риска, и в разрезе капитала по риску это видно сразу.
    #
    # Новое значение не требует миграции: перечисления хранятся строкой
    # (native_enum=False, проверка значений в базе не создаётся), и добавить
    # ещё одно можно правкой одного этого файла.
    CRYPTO = "crypto"
    LOAN = "loan"  # рассрочка или кредит наличными, без пластика
    OTHER = "other"


class AccountNature(str, enum.Enum):
    """Whether the account's balance adds to capital or subtracts from it.
    Split out of AccountKind so net worth can show "assets / liabilities /
    capital" as three honest numbers instead of one blended total: a store
    instalment account behaves exactly like a credit card even though its
    name says nothing about credit."""

    ASSET = "asset"
    LIABILITY = "liability"


class CategoryKind(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionType(str, enum.Enum):
    """INCOME and EXPENSE affect the earned/spent totals; TRANSFER never
    does — it only moves money that is already yours between your own
    accounts. EXTERNAL_IN and EXTERNAL_OUT are the third case the original
    model had no room for: money arriving from (or going to) another
    person. It changes an account balance but is not earnings, so the
    hourly-wage and savings-rate figures stay honest. Spreadsheets usually
    fake this with placeholder categories along the lines of "other income
    — transfers", which is exactly the workaround this replaces."""

    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    EXTERNAL_IN = "external_in"
    EXTERNAL_OUT = "external_out"


class SettlementKind(str, enum.Enum):
    """Whether an EXTERNAL_IN / EXTERNAL_OUT movement is expected to come
    back. A wife handing over grocery money and a friend borrowing until
    payday look identical on a bank statement but mean opposite things:
    only the second belongs in "who owes whom". Set per movement, never per
    counterparty — the same person both gifts and borrows.

    Хранится строкой без ограничения в базе (native_enum=False и без
    CHECK), поэтому новый вид не требует миграции — но требует решения, как
    он ведёт себя в долгах (см. services/settlement_service.py).
    """

    GIFT = "gift"  # безвозвратно, в долги не попадает
    LOAN_OUT = "loan_out"  # я дал в долг — мне должны
    LOAN_IN = "loan_in"  # я занял — я должен
    REPAYMENT = "repayment"  # погашение ранее возникшего долга
    # Деньги прошли через меня: получил от одного, передал другому.
    #
    # Отдельно от подарка, хотя считается так же — долга не создаёт. Разница
    # в смысле: «получено подарками 50 000» — число, которое врёт о жизни,
    # если это была касса на общий подарок или сбор на поездку. Такие деньги
    # никогда не были ни доходом, ни щедростью — они полежали на счёте и
    # ушли дальше.
    #
    # Не отдельный тип операции: транзит — это всегда ДВА движения, приход и
    # расход, часто в разные дни. Типом пришлось бы заводить пару transit_in
    # и transit_out, буква в букву повторяющую external_in и external_out, —
    # а тип операции держит на себе всю арифметику: знак в балансе, попадание
    # в заработок и траты, отчёты, бюджеты, планы, капитал. Вопрос же здесь
    # ровно тот, на который отвечает этот перечень: вернётся ли.
    TRANSIT = "transit"


class AssetClass(str, enum.Enum):
    """Net-worth categories tracked manually (Cash is derived from Account
    balances instead — see services/net_worth_service.py)."""

    INVESTMENTS = "investments"
    CRYPTO = "crypto"
    REAL_ESTATE = "real_estate"
    VEHICLES = "vehicles"
    PRECIOUS_METALS = "precious_metals"
    # Техника, мебель, инструменты — то, чем пользуются, а не во что
    # вложились. Отдельной строкой, потому что иначе всё это оседает в
    # «прочем», и у разбивки самым большим куском оказывается тот, который
    # ничего не называет.
    #
    # Это вид вещи, а не признак «личного пользования»: тот отвечает на
    # «можно ли это потратить» и живёт отдельной осью — сдаваемая квартира
    # недвижимость, но не личного пользования, а подаренный родителям
    # телефон личная вещь, но уже не ваша.
    PERSONAL_ITEMS = "personal_items"
    OTHER = "other"


class CapitalRole(str, enum.Enum):
    """How an asset behaves month to month — set by the user, not inferred:
    the same laptop can be a productive work tool (NEUTRAL) or dead weight
    (DRAIN) depending on how it's actually used, which isn't derivable from
    any stored data."""

    INCOME = "income"  # e.g. a rented-out apartment
    NEUTRAL = "neutral"  # e.g. a laptop used for work, furniture
    DRAIN = "drain"  # e.g. a personal car, an idle depreciating gadget


class RecurringFrequency(str, enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class CryptoTransactionType(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class RiskLevel(str, enum.Enum):
    """Risk of loss, not asset class — set by the user, not inferred: real
    estate can be a paid-off primary home (LOW) or a leveraged rental
    (HIGH), the same asset_class doesn't determine which. Cash is always
    LOW (see services/net_worth_service.py) — it's the zero-risk anchor an
    80/20-style allocation rule is measured against."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ParticipantKind(str, enum.Enum):
    """Who a transaction is for. A pet is a participant rather than a
    category branch on purpose: cat food is both "Питомцы → Корм" and "for
    Мурзик", and folding the name into the category tree would mean
    duplicating the whole branch per animal.

    Вид — только пометка. Запрета записать доход на питомца нет ни
    здесь, ни в сервисах — раньше здесь было написано обратное, и это
    было неправдой. Отсутствие запрета сознательное: проверка,
    которая отказывается сохранить запись, должна быть нужнее того,
    что она ломает, а доход на питомца — это просто странная строка, а не
    разъехавшийся баланс."""

    PERSON = "person"
    PET = "pet"


class UnitKind(str, enum.Enum):
    """What a unit measures. Drives normalisation: 1.5 л at 120 ₽ and
    500 мл at 55 ₽ are only comparable once both are expressed per litre,
    so every unit carries a factor to its kind's base unit (see
    models/unit.py). SERVICE exists for things that have no quantity at all
    — a subscription, a taxi ride — where the count is always 1."""

    MASS = "mass"  # база: грамм
    VOLUME = "volume"  # база: миллилитр
    COUNT = "count"  # база: штука
    LENGTH = "length"  # база: метр
    SERVICE = "service"  # без измерения, количество всегда 1


class GoalStatus(str, enum.Enum):
    """A goal's ending. The spreadsheet had one "Изъять" operation covering
    two opposite outcomes — money spent on what it was saved for, and money
    given up on and returned to the pot — and only the free-text comment
    told them apart — and in practice a fair share of goals end the second
    way."""

    ACTIVE = "active"
    ACHIEVED = "achieved"  # накопили и потратили по назначению
    CANCELLED = "cancelled"  # передумали, резерв снят обратно


class PlanFrequency(str, enum.Enum):
    """Как часто повторяется план.

    Сумма плана — за одно повторение, а в месяц попадает столько, сколько
    повторений в него укладывается. Так уже вёл себя ежедневный план
    (сумма за день × дни месяца), и остальные виды — то же правило с другим
    шагом: «каждые две недели по 1 000 ₽» в месяце с тремя понедельниками
    даёт 3 000 ₽, а не 2 000.

    Шаг («каждые N») лежит отдельно, в plans.repeat_every: «ежемесячно» и
    «раз в три месяца» — одна и та же частота с разным шагом, и заводить
    под них два значения перечисления значило бы дублировать весь расчёт.

    Индексации нет нигде и намеренно: когда цена изменилась, человек правит
    число, и оно действует вперёд, не переписывая прошлое.
    """

    ONE_OFF = "one_off"  # один раз, в своём месяце и больше нигде
    DAY = "day"  # каждые N дней
    WEEK = "week"  # каждые N недель, по выбранным дням недели
    MONTH = "month"  # каждые N месяцев
    YEAR = "year"  # каждые N лет, в выбранных месяцах


class PlanMonthDay(str, enum.Enum):
    """Какой день берётся внутри месяца у месячного и годового повторения.

    Чисел 29, 30 и 31 здесь нет намеренно: «31 февраля» не существует, и
    приложению пришлось бы молча решать за человека — сдвинуть на 28-е или
    пропустить месяц. Вместо этого есть отдельные пункты, которые говорят
    ровно то, что человек имел в виду: «последний день месяца» и «первый»
    или «последний рабочий день».

    Пусто (NULL) означает «число не важно»: повторение одно, и стоит оно на
    том же числе, с которого план начался. Так ведёт себя старый
    ежемесячный план, у которого дня не было вовсе.
    """

    DAY_OF_MONTH = "day_of_month"  # числа 1–28, можно несколько
    NTH_WEEKDAY = "nth_weekday"  # первый/второй/…/последний ПН…ВС
    LAST_DAY = "last_day"  # последний день месяца
    FIRST_WORKDAY = "first_workday"  # первый будний день месяца
    LAST_WORKDAY = "last_workday"  # последний будний день месяца


class InvestmentKind(str, enum.Enum):
    """Asset families inside the single investments engine. Kept as one
    engine with a filter rather than parallel modules: lots, cost basis and
    FIFO disposal are identical for a share and a coin, and duplicating
    them would mean fixing every bug twice."""

    STOCK = "stock"
    BOND = "bond"
    FUND = "fund"
    CRYPTO = "crypto"
    METAL = "metal"
    OTHER = "other"


class TradeSide(str, enum.Enum):
    """Replaces CryptoTransactionType above, which was crypto-only. Same two
    values, one engine."""

    BUY = "buy"
    SELL = "sell"
