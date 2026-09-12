/**
 * Склонение числительных.
 *
 * Понадобилось расписанию планов: «каждые 2 недели» и «каждые 5 недель» —
 * разные слова, а строка собирается из числа, которое человек только что
 * напечатал. Обойтись подстановкой «2 неделя» нельзя: такую подпись читать
 * неприятно, а под ней стоит сумма, и доверие к ней падает вместе с
 * грамматикой.
 *
 * Лежит отдельно от i18n намеренно: там плоский словарь «ключ — строка», а
 * здесь правило языка, у которого форм три и выбираются они арифметикой.
 */

/**
 * Русская форма: `[1, 2, 5]` — «день», «дня», «дней».
 *
 * Правило школьное: 11–14 всегда берут третью форму (одиннадцать дней), в
 * остальных случаях решает последняя цифра.
 */
export function pluralRu(count: number, forms: readonly [string, string, string]): string {
  const tail = Math.abs(count) % 100;
  if (tail > 10 && tail < 20) return forms[2];

  const last = tail % 10;
  if (last === 1) return forms[0];
  if (last > 1 && last < 5) return forms[1];
  return forms[2];
}

/** Английская форма: одна на единицу, вторая на всё остальное. */
export function pluralEn(count: number, one: string, many: string): string {
  return Math.abs(count) === 1 ? one : many;
}

/** Порядковое числительное по-английски: 1st, 2nd, 3rd, 4th, 21st. */
export function ordinalEn(value: number): string {
  const tail = value % 100;
  if (tail > 10 && tail < 20) return `${value}th`;
  const suffix = ["th", "st", "nd", "rd"][value % 10] ?? "th";
  return `${value}${suffix}`;
}
