from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class BudgetCreate(BaseModel):
    category_id: int
    monthly_limit: Decimal = Field(gt=0)


class BudgetUpdate(BaseModel):
    monthly_limit: Decimal = Field(gt=0)


class BudgetRead(BaseModel):
    id: int
    category_id: int
    category_name: str
    category_color: str
    category_icon: str | None
    monthly_limit: Decimal


class BudgetStatus(BaseModel):
    """One budgeted category's actual spend for a given month, compared
    against its limit."""

    # None у строки, выведенной из плана: своей записи в бюджетах у неё
    # нет, править и удалять её надо в «Планировании».
    budget_id: int | None
    # Откуда взялся лимит. Строка «из плана» ведёт себя иначе: меняется по
    # месяцам сама и не редактируется здесь.
    source: Literal["budget", "plan"] = "budget"
    category_id: int
    category_name: str
    category_color: str
    category_icon: str | None
    monthly_limit: Decimal
    spent: Decimal
    remaining: Decimal
    # Can exceed 100 — the UI clamps the progress bar fill, not this number,
    # so "spent 150% of budget" is still visible in the raw value.
    percent: float
    is_over_budget: bool


class BudgetStatusResponse(BaseModel):
    year: int
    month: int
    items: list[BudgetStatus]
