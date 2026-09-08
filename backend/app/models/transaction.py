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

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SettlementKind, TransactionType
from app.models.mixins import TimestampMixin
from app.models.tag import transaction_tags


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Публичный идентификатор записи. Целочисленный id остаётся первичным
    # ключом — на нём держатся все связи и он дешевле в индексах, — а UUID
    # используется наружу: он не подсказывает, сколько всего операций, и не
    # ломается при переносе данных между установками. В таблице колонка
    # скрыта по умолчанию.
    uuid: Mapped[uuid_lib.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, unique=True, index=True, default=uuid_lib.uuid4
    )

    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    # Destination account for TRANSFER-type rows only.
    transfer_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
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
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False, default=Decimal("1"))
    amount_base: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

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
    is_excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped["Account"] = relationship(back_populates="transactions", foreign_keys=[account_id])
    transfer_account: Mapped["Account | None"] = relationship(foreign_keys=[transfer_account_id])
    category: Mapped["Category | None"] = relationship(back_populates="transactions")
    participant: Mapped["Participant | None"] = relationship()
    store: Mapped["Store | None"] = relationship()
    counterparty: Mapped["Counterparty | None"] = relationship()
    tags: Mapped[list["Tag"]] = relationship(secondary=transaction_tags, back_populates="transactions")
    splits: Mapped[list["TransactionSplit"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", order_by="TransactionSplit.id"
    )
    items: Mapped[list["TransactionItem"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", order_by="TransactionItem.position"
    )


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
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
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
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)

    # Ссылка на справочник товаров — то, что склеивает десять чеков в одну
    # кривую цены. SET NULL: удаление товара не должно уносить позиции.
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    # Название как в чеке. Хранится всегда, даже когда товар выбран из
    # справочника: в магазине он мог называться иначе, и это важно помнить.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Категория позиции. Если не задана — берётся у транзакции целиком.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)

    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), nullable=True)
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
    category: Mapped["Category | None"] = relationship()
    unit: Mapped["Unit | None"] = relationship()
