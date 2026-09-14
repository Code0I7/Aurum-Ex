"""Пара операций, про которую человек сказал «это разные».

Приложение ищет перевод между своими счетами, записанный дважды (см.
services/transfer_match_service.py), и только предлагает склеить — само не
склеивает никогда. Совпадение по сумме и дате бывает и честным: сто рублей
на наличные в понедельник и сто рублей зарплатного аванса на карту в тот же
день — не один перевод. Отказ нужно помнить, иначе та же пара возвращалась
бы в список после каждой загрузки страницы и отучила бы в него смотреть.

Хранится именно пара, а не отметка на операции: операция, честно отличная
от одной соседки, может оказаться повтором другой.
"""
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TransferMatchDismissal(Base):
    __tablename__ = "transfer_match_dismissals"

    # Меньший номер всегда первым: одна пара — одна строка, в каком бы
    # порядке её ни отклонили.
    #
    # CASCADE: удалённая операция уносит и решения о себе. Пара без одной
    # из сторон ничего не значит.
    first_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True
    )
    second_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True, index=True
    )
