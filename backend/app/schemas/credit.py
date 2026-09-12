"""Схемы условий по кредиту.

Ставка хранится и передаётся так, как её называет банк: 24.9 — это 24.9, а
не 0.249. Значение должно сверяться глазами с договором без пересчёта в
уме, иначе ошибка в сто раз останется незамеченной.
"""
from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field


class CreditTermsWrite(BaseModel):
    annual_rate_percent: Decimal | None = Field(default=None, ge=0, le=1000)
    credit_limit: Decimal | None = Field(default=None, ge=0)
    # Беспроцентный период: 120 дней у рассрочки, 55 у типичной карты.
    grace_days: int | None = Field(default=None, ge=0, le=1000)
    # День месяца, когда банк ждёт платёж. 31 допустим: в коротком месяце он
    # прижимается к последнему дню (см. credit_service.next_payment_date).
    payment_day: int | None = Field(default=None, ge=1, le=31)
    minimum_payment: Decimal | None = Field(default=None, ge=0)
    opened_on: date_ | None = None
    closes_on: date_ | None = None
    notes: str | None = Field(default=None, max_length=500)


class CreditTermsRead(CreditTermsWrite):
    account_id: int
    account_name: str
    # Валюта счёта. Долг по долларовой карте — это доллары, и подписывать
    # его значком валюты установки значит называть сумму неверно.
    account_currency: str = ""
    # Долг положительным числом: баланс счёта отрицателен, но «должен 12 300»
    # читается легче, чем «баланс −12 300».
    debt: Decimal
    # Производное от лимита и долга. None, когда лимит не задан: у обычного
    # кредита его нет, и показывать «доступно 0» было бы неправдой.
    available: Decimal | None = None
    used_percent: float | None = None
    # Оценка, а не банковское число: льготный период и точный счёт дней здесь
    # не воспроизводятся.
    estimated_monthly_interest: Decimal | None = None


class CreditSummary(BaseModel):
    """Итог для карточки долгов."""

    debt: Decimal
    estimated_monthly_interest: Decimal
