"""A single money movement: income, expense, a transfer between your own
accounts, or a settlement with someone outside the household.

Three additions over the original model shape the rest of the app:

  * every row carries a UUID alongside its integer id, and an explicit
    position within its day. Without the second one, three operations dated
    26.08.2024 sort arbitrarily and the running balance appears to dive
    below zero on a day where it never did;
  * the amount is stored twice — in the currency it happened in, and
    converted to the base currency at that day's rate, which is frozen into
    the row. Recomputing history from today's rate would rewrite the past
    every morning;
  * a row can be marked "not counted" instead of deleted. The source
    spreadsheet faked this by zeroing the quantity (8 records: a returned
    phone, refunded headphones, a cancelled order) because a purchase you
    want to remember but not count had nowhere else to live.
"""
import uuid as uuid_lib
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SettlementKind, TransactionType
from app.models.mixins import TimestampMixin
from app.models.tag import transaction_tags


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    # Список всегда читается одним порядком — по дате, затем по месту
    # внутри дня. Без этого индекса каждая страница читала таблицу
    # целиком и сортировала в памяти: на двух тысячах строк это 2 мс, на
    # пятидесяти тысячах — восемь, и дальше пропорционально росту базы.
    __table_args__ = (Index("ix_transactions_date_day_order", "date", "day_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Публичный идентификатор записи. Целочисленный id остаётся первичным
    # ключом — на нём держатся все связи и он дешевле в индексах, — а UUID
    # используется наружу: он не подсказывает, сколько всего операций, и не
    # ломается при переносе данных между установками. В таблице колонка
    # скрыта по умолчанию.
    uuid: Mapped[uuid_lib.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, unique=True, index=True, default=uuid_lib.uuid4
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Destination account for TRANSFER-type rows only.
    transfer_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Кто участник операции — человек или питомец. Необязательное поле:
    # комиссия банка и проценты по кредиту не относятся ни к кому.
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="SET NULL"), nullable=True
    )
    # Магазин, где произошла покупка. Вместе с позициями чека даёт ответ на
    # вопрос "где этот товар дешевле".
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id", ondelete="SET NULL"), nullable=True)
    # Человек вне домохозяйства для EXTERNAL_IN / EXTERNAL_OUT.
    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id", ondelete="SET NULL"), nullable=True
    )
    # Вторая сторона транзита, и только его.
    #
    # Транзит проходит между двумя людьми: брат передал на покупки для мамы,
    # покупки сделаны для мамы. С одним полем в записи оказывались брат у
    # прихода и мама у расхода, и сложить их было не по чему — приложение
    # писало «брату осталось 4 500» и «маме недодал 4 870», оба числа
    # бессмысленны, потому что стороны разные.
    #
    #   приход — counterparty кто передал, transit_party для кого;
    #   расход — counterparty кому ушло,  transit_party чьи деньги.
    #
    # Сложение идёт по «для кого»: получено для мамы минус потрачено на маму.
    # Источник в расчётах не появляется — он не сторона: ни он никому не
    # должен, ни ему.
    #
    # У подарка и займа второй стороны нет: там деньги и правда между двумя.
    transit_party_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id", ondelete="SET NULL"), nullable=True, index=True
    )

    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", native_enum=False, length=15), nullable=False
    )
    # Возвратность расчёта с контрагентом: подарок долга не создаёт, заём
    # создаёт. Ставится на операции, а не на контрагенте — один и тот же
    # человек и дарит, и одалживает.
    settlement_kind: Mapped[SettlementKind | None] = mapped_column(
        Enum(SettlementKind, name="settlement_kind", native_enum=False, length=15), nullable=True
    )

    # Always stored positive; `type` carries the sign/direction.
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Валюта операции и та же сумма в базовой валюте. Курс заморожен в
    # строке: пересчёт по сегодняшнему курсу переписывал бы прошлое.
    # Значение по умолчанию нужно только на уровне БД, чтобы колонка не
    # была пустой при прямой вставке. Настоящая валюта приходит из
    # настроек приложения (см. services/currency_service.get_base_currency)
    # или со счёта операции.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    # Пустые, когда курса на дату операции нет.
    #
    # Раньше здесь молча стояла единица: покупка на 50 $ становилась 50 ₽ в
    # отчётах, и число выглядело как обычное. Пустота говорит правду —
    # «пересчитать пока не из чего», — и такая операция в итоги не входит, а
    # под ними сказано, сколько таких пропущено.
    #
    # Курс прошедшего дня не меняется никогда, поэтому дотянуть его позже и
    # пересчитать — не «переписать прошлое», а записать его впервые.
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 10), nullable=True)
    amount_base: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    # Вторая сторона перевода между разными валютами: сколько пришло, в чём
    # и сколько это в валюте установки.
    #
    # Пока обе карты в одной валюте, второй суммы не существует: сколько
    # ушло, столько и пришло, и колонки пустые. Между валютами равенство
    # ломается — сто евро уходят с евровой карты, а на рублёвую приходит
    # столько, сколько решил банк своим курсом и своей комиссией. Вывести
    # это число из курса ЦБ нельзя: оно ему не равно и равняться не обязано,
    # а разница между сторонами и есть цена перевода, которую видно только
    # так.
    #
    # Поэтому вторая сумма — данные, а не расчёт: её переписывают из
    # выписки. Пустота означает «равна первой», а не «неизвестна».
    transfer_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    transfer_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    transfer_amount_base: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    # Необязательно. В исходной таблице это была вторая строка записи, а не
    # заметка к ней: у большинства покупок сказать сверх категории нечего.
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Историческое свободнотекстовое поле продавца. Заполняется только
    # CSV-импортом банковской выписки, где магазин приходит строкой и ещё
    # не сопоставлен со справочником; в форме ввода поля нет — там для
    # этого есть «Магазин», и два поля об одном приводили к тому, что
    # сравнение цен молча теряло половину покупок.
    #
    # Смысловая связь живёт в store_id.
    merchant: Mapped[str | None] = mapped_column(String(150), nullable=True)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    # Порядок внутри дня. Заполняется автоматически по времени создания и
    # правится перетаскиванием строки; между днями строка не переносится.
    day_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Запись видна в истории, но в суммы, бюджеты и графики не входит.
    #
    # Главный случай — возвращённая покупка. Признак означает «этого расхода
    # не было», причём с самой даты покупки, а не с даты возврата: покупка
    # аннулирована, значит её не было вовсе. Пока возврат в пути, деньги
    # по-прежнему принадлежат человеку — у него требование к магазину на эту
    # сумму, — поэтому приложение показывает более верную картину, чем
    # остаток на карте. Расхождение с банком в эти дни — не ошибка, а разница
    # между «что у меня есть» и «что успело вернуться».
    #
    # Чего признак НЕ описывает: частичный возврат. Если удержали доставку
    # или комиссию за отказ, эта часть действительно потрачена, и её нужно
    # занести отдельной тратой — иначе она пропадёт вместе с исключённой
    # покупкой.
    is_excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped["Account"] = relationship(back_populates="transactions", foreign_keys=[account_id])
    transfer_account: Mapped["Account | None"] = relationship(foreign_keys=[transfer_account_id])
    category: Mapped["Category | None"] = relationship(back_populates="transactions")
    participant: Mapped["Participant | None"] = relationship()
    store: Mapped["Store | None"] = relationship()
    # Колонок на контрагентов теперь две, и SQLAlchemy сама выбрать между
    # ними не может — приходится назвать нужную явно.
    counterparty: Mapped["Counterparty | None"] = relationship(foreign_keys=[counterparty_id])
    transit_party: Mapped["Counterparty | None"] = relationship(foreign_keys=[transit_party_id])
    tags: Mapped[list["Tag"]] = relationship(secondary=transaction_tags, back_populates="transactions")
    splits: Mapped[list["TransactionSplit"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", order_by="TransactionSplit.id"
    )
    # Разбивка по людям — вторая ось, независимая от категорий: та отвечает
    # на «на что», эта на «от кого» (см. TransactionCounterpartySplit).
    counterparty_splits: Mapped[list["TransactionCounterpartySplit"]] = relationship(
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionCounterpartySplit.id",
    )
    items: Mapped[list["TransactionItem"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", order_by="TransactionItem.position"
    )


class TransactionCounterpartySplit(Base):
    """Доля одного человека в операции, которую разделили между несколькими.

    Долг вернули трое одним переводом. В выписке банка это одна операция, и
    три записи в приложении означали бы, что оно перестало сходиться с
    выпиской — ровно та причина, по которой у операции когда-то появилась
    разбивка по категориям.

    Замена Transaction.counterparty_id, а не дополнение к нему: у
    разделённой операции контрагент пуст, а вместо него две или больше
    таких строк, и их суммы обязаны сойтись с суммой операции.

    Ось здесь своя, отдельная от категорий: та отвечает на «на что»,
    эта — на «от кого». Одна операция может быть разделена по обеим сразу,
    и каждая разбивка сходится с суммой самостоятельно.

    Вид расчёта (заём, безвозвратно, транзит) живёт на самой операции:
    трое, вернувшие долг, вернули именно долг. Понадобится свой у
    каждого — добавится колонкой сюда.

    counterparty_id допускает пустоту и SET NULL по той же причине, что и
    категория в разбивке: удаление человека не должно ломать чтение
    операции, в которой он когда-то был.
    """

    __tablename__ = "transaction_counterparty_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="counterparty_splits")
    counterparty: Mapped["Counterparty | None"] = relationship()


class TransactionSplit(Base):
    """One category's slice of a transaction whose amount is divided across
    several categories (one receipt, several kinds of goods) — an
    alternative to Transaction.category_id, not an addition to it: a split
    transaction has category_id=NULL and two or more of these instead, and
    their amounts must add up to the parent's amount exactly (see
    schemas/transaction.py's split_rule_violation).

    category_id is nullable + SET NULL, same as Transaction.category_id
    itself — deleting a category must not break *reading* a split that used
    to point at it, only creating/editing one requires a live category (see
    routes/transactions.py, and the same lesson already applied to
    transfer_account_id)."""

    __tablename__ = "transaction_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="splits")
    category: Mapped["Category | None"] = relationship()


class TransactionItem(Base):
    """One line of a receipt: what was bought, how much of it, at what price.

    Not the same thing as TransactionSplit above, and the two coexist. A
    split answers "which categories does this money belong to" and must add
    up to the parent exactly. A line item answers "what was in the bag", and
    deliberately need not add up to anything:

      * `price` and `amount` are optional — remembering that bread and milk
        were bought without remembering their prices is a normal, common
        case, and refusing to store that would lose the memory entirely;
      * the transaction's own amount stays the source of truth. When items
        cover only part of it, the UI shows the unallocated remainder rather
        than forcing the numbers to reconcile;
      * a transaction with no items at all is perfectly valid — quick entry
        stays one action, and a receipt is only itemised when the user cares.

    Quantity plus unit is what makes price tracking real: `amount` divided by
    (`quantity` × the unit's factor) gives a price per base unit, so 1.5 л at
    120 ₽ and 500 мл at 55 ₽ finally become comparable. Items without a price
    simply never reach the price chart — they are memory, not measurement.
    """

    __tablename__ = "transaction_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Ссылка на справочник товаров — то, что склеивает десять чеков в одну
    # кривую цены. SET NULL: удаление товара не должно уносить позиции.
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Название как в чеке. Хранится всегда, даже когда товар выбран из
    # справочника: в магазине он мог называться иначе, и это важно помнить.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Категории у позиции нет намеренно. Она здесь была, её можно было
    # задать — и ни один отчёт её не читал: деньги считаются по категории
    # операции и по её сплитам (services/category_rollup.py). Поле, которое
    # хранится, но никуда не идёт, хуже отсутствующего: на него смотрят и
    # делают выводы. Разложить чек по категориям можно сплитами.

    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), nullable=True)

    # Размер одной упаковки: «2 шт × 0,9 л». Нужен, чтобы штуки было с чем
    # сравнивать: без него «1 шт за 89 ₽» и «900 мл за 89 ₽» — числа разных
    # родов, и общей кривой цены у них нет.
    #
    # Лежит здесь, а не в товаре, и это главное решение. В товаре это было
    # бы одно число на всю историю: производитель ужал литр до 900 мл — и
    # прошлые покупки пересчитались бы по новому размеру, спрятав ровно то
    # подорожание, ради которого учёт цен и ведут. Здесь размер остаётся
    # тем, что был в день покупки, навсегда.
    #
    # Необязателен, и это тоже намеренно. Развесной товар, расфасованный в
    # магазине, каждый раз весит по-своему: раз человек переписал вес с
    # ценника, другой раз забыл. Забытый вес — не повод придумывать его из
    # прошлой покупки; такая позиция просто не даёт точки на кривой «за
    # килограмм», оставаясь на кривой «за упаковку».
    pack_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    pack_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("units.id", ondelete="SET NULL"), nullable=True
    )

    # Цена за БАЗОВУЮ меру своего вида — за килограмм, за литр, за штуку, —
    # а не за введённую единицу.
    #
    # Так написано на ценнике и так сравнивают в магазине. Цена за
    # введённую единицу выглядела бы «0,074» у пол-литра воды: число
    # арифметически верное, но бесполезное, и человек решает, что
    # приложение сломалось.
    #
    # Отсюда и связь с суммой: amount = quantity × factor × price. Для
    # 500 мл по 73,98 за литр это 500 × 0,001 × 73,98 = 36,99.
    #
    # Оба поля необязательны; когда заданы оба, сходимость не проверяется —
    # в чеках встречается округление до копейки.
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    # Заметка на уровне позиции — отдельно от заметки транзакции: "тот самый
    # чай, который понравился" относится к товару, а не к походу в магазин.
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    transaction: Mapped["Transaction"] = relationship(back_populates="items")
    product: Mapped["Product | None"] = relationship()
    # Две ссылки на один справочник — единицу приходится называть явно,
    # иначе SQLAlchemy не знает, по какой из них строить связь.
    unit: Mapped["Unit | None"] = relationship(foreign_keys=[unit_id])
    pack_unit: Mapped["Unit | None"] = relationship(foreign_keys=[pack_unit_id])
