import { getCurrency, getLanguage, type Language } from "@/lib/i18n";

/** Maps our app language to the Intl locale used for number/date formatting. */
export function getIntlLocale(language: Language = getLanguage()): string {
  return language === "ru" ? "ru-RU" : "en-US";
}

// `currency` defaults to the app's primary currency setting (Settings page)
// — call sites only need to pass it explicitly when formatting a value known
// to be in a *different* currency than that setting.
export function formatCurrency(amount: number | string, currency: string = getCurrency()): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  return new Intl.NumberFormat(getIntlLocale(), {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatSignedCurrency(amount: number | string, currency: string = getCurrency()): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatCurrency(value, currency)}`;
}

/** "Hide balance" masking — wraps an already-formatted amount (currency,
 * quantity, whatever reveals a dollar figure) rather than reformatting it,
 * so call sites don't need a separate hidden-vs-shown branch for every
 * number. Percentages are deliberately never masked by callers — a % move
 * doesn't reveal how much money is actually involved. */
export function maskAmount(formatted: string, hidden: boolean): string {
  return hidden ? "••••" : formatted;
}

const MONTH_LABELS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;
const MONTH_LABELS_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"] as const;

export function getMonthLabels(language: Language): readonly string[] {
  return language === "ru" ? MONTH_LABELS_RU : MONTH_LABELS_EN;
}

/** `includeYear` is for contexts spanning multiple years (e.g. an all-time
 * search) where "Aug 16" alone wouldn't say which year. */
export function formatTransactionDate(isoDate: string, includeYear = false): string {
  const date = new Date(`${isoDate}T00:00:00`);
  return new Intl.DateTimeFormat(getIntlLocale(), {
    month: "short",
    day: "numeric",
    year: includeYear ? "numeric" : undefined,
  }).format(date);
}

/** Russian noun pluralization: pick the right form for 1/2-4/5+ (with the
 * 11-14 exception), e.g. pluralizeRu(3, "актив", "актива", "активов"). */
export function pluralizeRu(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}
