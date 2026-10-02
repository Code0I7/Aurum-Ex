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

/**
 * Сколько часов в рабочем дне, когда своих данных нет вовсе.
 *
 * Восемь — общепринятая мера, и для пустой установки она лучше отказа. Но
 * это именно последнее средство: у человека с днём в 10,5 часа покупка
 * показывалась на треть дороже, чем стоила, а у человека с днём 5,5 — на
 * треть дешевле. Своя длина дня считается на сервере из введённых часов и
 * дней, см. dayHoursForDate.
 */
const FALLBACK_HOURS_PER_DAY = 8;

export interface HourlyRates {
  /** «Год-месяц» → ставка за час для покупок этого месяца. */
  months: Record<string, string>;
  /** Средняя за всё время. null, когда часов не введено вовсе. */
  overall: string | null;
  /** Длина рабочего дня в часах — тем же окном, что и ставка. Нужна, чтобы
   *  перевести часы в дни: восьмичасовой день здесь был чужой меркой. */
  day_hours: {
    months: Record<string, string>;
    overall: string | null;
  };
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
 * Длина рабочего дня для месяца операции.
 *
 * Та же лестница, что у ставки: сначала свой месяц, потом средняя за всё
 * время, и только если часов с днями не введено нигде — восемь часов.
 * Покупка 2022 года переводится в дни по дню 2022 года: если тогда работали
 * по 5,5 часа, то двадцать два часа — это четыре дня, а не два с половиной.
 */
export function dayHoursForDate(rates: HourlyRates | undefined, isoDate: string): number {
  const own = rates?.day_hours;
  if (!own) return FALLBACK_HOURS_PER_DAY;
  const value = Number(own.months[isoDate.slice(0, 7)] ?? own.overall ?? 0);
  return value > 0 ? value : FALLBACK_HOURS_PER_DAY;
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
export function formatWorkCost(
  amount: number | string,
  rate: number | null,
  dayHours: number = FALLBACK_HOURS_PER_DAY
): string | null {
  if (rate === null || rate <= 0) return null;
  const value = Math.abs(Number(amount));
  if (!Number.isFinite(value) || value === 0) return null;

  // Единицы через перевод, а не строкой в коде: «мин/ч/дн» в английском
  // интерфейсе выглядели бы недоделкой.
  const hours = value / rate;
  if (hours < 1) return `${Math.round(hours * 60)} ${t("hours.minutes")}`;

  // Порог тот же, что и делитель: пока покупка не стоит целого рабочего
  // дня, показывать её в днях нечем.
  const perDay = dayHours > 0 ? dayHours : FALLBACK_HOURS_PER_DAY;
  if (hours < perDay) return `${decimal(hours)} ${t("hours.hours")}`;

  const days = hours / perDay;
  // До десяти дней десятая доля ещё различима, дальше — округление до дня:
  // «23,4 дня» точнее, чем нужно, чтобы ужаснуться.
  return `${days < 10 ? decimal(days) : String(Math.round(days))} ${t("hours.days")}`;
}

/** Та же цена, но часами и всегда — для подсказки под курсором.
 *
 * Дни отвечают на «сколько это в моей работе», часы остаются точным
 * числом за ними: «26 раб. дн.» не должно прятать, что это 272 часа. */
export function formatWorkHours(amount: number | string, rate: number | null): string | null {
  if (rate === null || rate <= 0) return null;
  const value = Math.abs(Number(amount));
  if (!Number.isFinite(value) || value === 0) return null;
  return `${decimal(value / rate)} ${t("hours.hours")}`;
}
