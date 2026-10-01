"""Доля прошедшего месяца в заработке за час.

Часы вводятся на месяц целиком — это план, а не журнал смен. Пока месяц
идёт, делить доход на весь план нечестно: первого числа выходит, что
человек заработал два рубля в час, потому что доход у него за один день, а
часы за тридцать. Проверяется, что пара «доход и часы» всегда описывает
один и тот же срок.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.services.hourly_service import elapsed_hours


def test_finished_month_counts_whole():
    """Месяц закончился — засчитывается всё, что в нём отработано."""
    assert elapsed_hours(2026, 8, Decimal("300"), today=date(2026, 9, 9)) == Decimal("300")


def test_future_month_counts_nothing():
    """В ещё не наступившем месяце нет ни часов, ни заработка. Засчитать
    часы значило бы поделить сегодняшний доход на будущее время."""
    assert elapsed_hours(2026, 10, Decimal("300"), today=date(2026, 9, 9)) == Decimal("0")


@pytest.mark.parametrize(
    "day, expected",
    [
        # Сентябрь — 30 дней. Первое число: прошёл один день из тридцати.
        (1, Decimal("10")),
        (15, Decimal("150")),
        (30, Decimal("300")),
    ],
)
def test_current_month_counts_elapsed_share(day, expected):
    assert elapsed_hours(2026, 9, Decimal("300"), today=date(2026, 9, day)) == expected


def test_today_counts_as_worked():
    """Смену отрабатывают в тот же день, когда её записывают: считать
    сегодняшний день не наступившим значило бы обнулять часы первого числа
    и не показывать заработок вовсе."""
    assert elapsed_hours(2026, 9, Decimal("300"), today=date(2026, 9, 1)) > 0


def test_the_case_from_the_report():
    """Ровно то, на что жаловались: 277,88 часа плана и доход за один день
    давали два рубля в час. С поправкой на прошедшее — сотни."""
    hours = elapsed_hours(2026, 9, Decimal("277.88"), today=date(2026, 9, 1))
    income = Decimal("1600")
    assert income / hours > Decimal("150")
