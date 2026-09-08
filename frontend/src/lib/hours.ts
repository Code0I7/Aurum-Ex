/**
 * Перевод суммы в отработанное время.
 *
 * Смысл не в самой цифре, а в единице измерения: цена в рублях привычна и
 * потому почти не ощущается, цена в рабочих днях ощущается сразу. «Этот
 * монитор стоил мне четыре дня» доходит быстрее, чем «17 273 ₽».
 */

/** Сколько часов в рабочем дне. Восемь — не догма, но общепринятая мера, и
 *  считать день восьмичасовым понятнее, чем спрашивать длину смены. */
const HOURS_PER_DAY = 8;

export interface HourlyRates {
  /** Год → ставка за час в этом году. */
  years: Record<string, string>;
  /** Средняя за всё время. null, когда часов не введено вовсе. */
  overall: string | null;
}

/**
 * Ставка, по которой считать конкретную операцию.
 *
 * Берётся ставка её года: за четыре года заработок меняется втрое, и покупка
 * 2022 года по сегодняшней ставке выглядела бы втрое дешевле, чем была.
 * Помесячно считать нельзя — доход приходит рывками, и цифра превращается в
 * шум. Год без введённых часов падает на среднюю: человек работал и тогда,
 * просто не записал сколько.
 */
export function rateForDate(rates: HourlyRates | undefined, isoDate: string): number | null {
  if (!rates) return null;
  const yearly = rates.years[isoDate.slice(0, 4)];
  const value = Number(yearly ?? rates.overall ?? 0);
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

  const hours = value / rate;
  if (hours < 1) return `${Math.round(hours * 60)} мин`;
  if (hours < HOURS_PER_DAY) return `${hours.toFixed(1).replace(".", ",")} ч`;

  const days = hours / HOURS_PER_DAY;
  // До десяти дней десятая доля ещё различима, дальше — округление до дня:
  // «23,4 дня» точнее, чем нужно, чтобы ужаснуться.
  return days < 10 ? `${days.toFixed(1).replace(".", ",")} дн` : `${Math.round(days)} дн`;
}
