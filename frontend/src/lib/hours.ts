import { getIntlLocale } from "@/lib/format";
import { t } from "@/lib/i18n";

/**
 * Перевод суммы в отработанное время.
 *
 * Смысл не в самой цифре, а в единице измерения: цена в рублях привычна и
 * потому почти не ощущается, цена в рабочих днях ощущается сразу. «Этот
 * монитор стоил мне четыре дня» доходит быстрее, чем «17 273 ₽».
 */

/** Одна десятая в письме своего языка: «4,2» по-русски и «4.2»
 *  по-английски. Локаль берётся та же, что у сумм. */
function decimal(value: number): string {
  return value.toLocaleString(getIntlLocale(), {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

/** Сколько часов в рабочем дне. Восемь — не догма, но общепринятая мера, и
 *  считать день восьмичасовым понятнее, чем спрашивать длину смены. */
const HOURS_PER_DAY = 8;

export interface HourlyRates {
  /** «Год-месяц» → ставка за час для покупок этого месяца. */
  months: Record<string, string>;
  /** Средняя за всё время. null, когда часов не введено вовсе. */
  overall: string | null;
}

/**
 * Ставка, по которой считать конкретную операцию.
 *
 * Берётся ставка её месяца — а сервер считает её скользящим окном в три
 * месяца, заканчивающимся этим же месяцем. Не сегодняшняя ставка: за четыре
 * года заработок меняется втрое, и покупка 2022 года по нынешнему заработку
 * выглядела бы втрое дешевле, чем была. Не за один месяц: доход приходит
 * рывками, и месяц без зарплаты давал бы копейки в час.
 *
 * Месяц, для которого ставки нет, падает на среднюю за всё время: человек
 * работал и тогда, просто в окне не набралось часов.
 */
export function rateForDate(rates: HourlyRates | undefined, isoDate: string): number | null {
  if (!rates) return null;
  // Ключ отрезается от строки даты, а не собирается из Date: разбор даты
  // втянул бы часовой пояс, и покупка первого числа съезжала бы в
  // предыдущий месяц.
  const monthly = rates.months[isoDate.slice(0, 7)];
  const value = Number(monthly ?? rates.overall ?? 0);
  return value > 0 ? value : null;
}

/**
 * Стоимость в рабочем времени, готовой строкой.
 *
 * Единица выбирается по величине: минуты для мелочи, часы до рабочего дня,
 * дни дальше. Показывать «0,03 дня» за проезд на автобусе так же бесполезно,
 * как «112 часов» за монитор.
 *
 * null означает «посчитать не из чего» — часов не введено. Ноль вместо этого
 * означал бы, что покупка досталась даром.
 */
export function formatWorkCost(amount: number | string, rate: number | null): string | null {
  if (rate === null || rate <= 0) return null;
  const value = Math.abs(Number(amount));
  if (!Number.isFinite(value) || value === 0) return null;

  // Единицы через перевод, а не строкой в коде: «мин/ч/дн» в английском
  // интерфейсе выглядели бы недоделкой.
  const hours = value / rate;
  if (hours < 1) return `${Math.round(hours * 60)} ${t("hours.minutes")}`;
  if (hours < HOURS_PER_DAY) return `${decimal(hours)} ${t("hours.hours")}`;

  const days = hours / HOURS_PER_DAY;
  // До десяти дней десятая доля ещё различима, дальше — округление до дня:
  // «23,4 дня» точнее, чем нужно, чтобы ужаснуться.
  return `${days < 10 ? decimal(days) : String(Math.round(days))} ${t("hours.days")}`;
}
