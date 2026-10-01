import { getCurrency, getLanguage, getShowCents, t, type Language } from "@/lib/i18n";

/** Maps our app language to the Intl locale used for number/date formatting. */
export function getIntlLocale(language: Language = getLanguage()): string {
  return language === "ru" ? "ru-RU" : "en-US";
}

/**
 * Валюта, в которой печатать сумму, — с запасным вариантом.
 *
 * Пустая строка сюда приходит буднично: у карточки капитала валюта берётся
 * из ответа сервера, а пока ответ не пришёл, её нет. Intl на пустой код
 * отвечает не пустой подписью, а исключением — и страница не открывается
 * вовсе. Вкладка «Капитал» так и упала.
 *
 * Поэтому проверка живёт здесь, одна на все места форматирования: место,
 * забывшее подставить валюту, покажет сумму в валюте установки, но покажет.
 */
function resolveCurrency(currency: string | null | undefined): string {
  return currency && currency.trim() ? currency : getCurrency();
}

// `currency` defaults to the app's primary currency setting (Settings page)
// — call sites only need to pass it explicitly when formatting a value known
// to be in a *different* currency than that setting.
export function formatCurrency(amount: number | string, currency?: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  // Копейки — настройка (Настройки → Точное отображение). В самой операции
  // они и есть данные: 36,99, показанные как 37, — уже не то, что
  // записано, и столбец из таких строк не сходится в сумму, а человек ищет
  // ошибку там, где её нет. В годовых итогах они, наоборот, только
  // удлиняют число, поэтому выбор оставлен человеку.
  const cents = getShowCents() ? 2 : 0;
  return new Intl.NumberFormat(getIntlLocale(), {
    style: "currency",
    currency: resolveCurrency(currency),
    minimumFractionDigits: cents,
    maximumFractionDigits: cents,
  }).format(value);
}

/** Same currency formatting as formatCurrency, but scales decimal precision
 * down to the value's own magnitude instead of always rounding to whole
 * units — a low-cap memecoin can genuinely price at $0.000000006894, and
 * formatCurrency's fixed 0 fraction digits would render that as "$0",
 * indistinguishable from actually being worthless. Values >= 1 still show
 * just 2 decimals (a coin price doesn't need more than cents once it's
 * above a dollar). For the Crypto tab's per-coin price/holdings/avg-buy-price
 * cells and per-transaction price — anywhere a single coin's own value
 * needs to be told apart from zero, not just a portfolio-wide total. */
function significantFractionDigits(value: number): number {
  const abs = Math.abs(value);
  return abs === 0 || abs >= 1
    ? 2
    : // Leading zeros right after the decimal point before the first
      // significant digit, plus 4 more digits of real precision beyond
      // that — e.g. 0.000000006894 has 8 leading zeros, so this shows
      // 12 decimal places, landing exactly on "6894" and nothing more.
      Math.min(20, Math.max(0, -Math.floor(Math.log10(abs)) - 1) + 4);
}

export function formatCryptoAmount(amount: number | string, currency?: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  return new Intl.NumberFormat(getIntlLocale(), {
    style: "currency",
    currency: resolveCurrency(currency),
    maximumFractionDigits: significantFractionDigits(value),
  }).format(value);
}

/**
 * Курс валюты: столько единиц валюты установки за одну единицу другой.
 *
 * Не formatCurrency: тот показывает деньги, а деньги округляются до копеек
 * — и до целых рублей, если человек выключил точное отображение. Курс так
 * округлять нельзя: у слабых валют значащие цифры начинаются после
 * запятой, и «0 ₽ за тенге» — это не округление, а ошибка на вид.
 *
 * Точность та же, что у крипты, и по той же причине: число может быть
 * любой величины, а знаков нужно ровно столько, чтобы отличить его от
 * нуля и от соседнего.
 */
export function formatRate(rate: number | string, currency?: string): string {
  const value = typeof rate === "string" ? Number(rate) : rate;
  return new Intl.NumberFormat(getIntlLocale(), {
    style: "currency",
    currency: resolveCurrency(currency),
    maximumFractionDigits: significantFractionDigits(value),
  }).format(value);
}

export function formatSignedCurrency(amount: number | string, currency?: string): string {
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

/** Strips trailing zeros from a decimal string for pre-filling an editable
 * number input — the backend stores crypto quantity/price as Numeric(38,18)
 * and returns it at full scale (e.g. "3.000000000000000000"), which is
 * correct for computation but not something anyone wants to see or edit
 * around in a form field. Works on the string directly rather than via
 * Number(), which would round a genuine 18-decimal-place amount (a
 * wei-level token quantity) through floating point instead of just
 * trimming the padding. */
export function trimTrailingZeros(value: string): string {
  if (!value.includes(".")) return value;
  const trimmed = value.replace(/0+$/, "").replace(/\.$/, "");
  // «-0» тоже ноль: от «-0.000» после обрезки остаётся минус перед нулём, и
  // в поле ввода он выглядит опечаткой. Нашлось тестом — на настоящих
  // количествах такого не бывает, они положительные.
  if (trimmed === "" || trimmed === "-" || trimmed === "-0") return "0";
  return trimmed;
}

/** Количество бумаг, монет или единиц товара — для показа, не для ввода.
 *
 * База хранит количество с запасом знаков после запятой: крипту дробят до
 * восьмого, а то и до восемнадцатого. Акциям этот запас не нужен, и
 * «30.00000000 × 4 000,00 ₽» в списке читается как ошибка расчёта, хотя
 * это просто хвост нулей. Лишние нули отбрасываются, значащие знаки
 * остаются все до единого.
 *
 * Целая часть группируется через Intl, дробная приклеивается строкой:
 * пропускать её через Number() значило бы округлить настоящее количество
 * токена в восемнадцать знаков ради красивой записи. */
export function formatQuantity(value: number | string): string {
  const trimmed = trimTrailingZeros(String(value));
  const negative = trimmed.startsWith("-");
  const [whole, fraction] = trimmed.replace("-", "").split(".");
  const locale = getIntlLocale();
  const grouped = new Intl.NumberFormat(locale).format(BigInt(whole || "0"));
  // Разделитель берётся у самой локали: запятая в русском, точка в английском.
  const separator = (1.1).toLocaleString(locale).replace(/[0-9]/g, "");
  return `${negative ? "-" : ""}${grouped}${fraction ? separator + fraction : ""}`;
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

/** Месяц тремя буквами для подписей осей: «янв», «фев». Даты на графике
 * подписываются коротко — полное название съедает место, которого на узкой
 * оси нет. */
export function formatMonthShort(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  return new Intl.DateTimeFormat(getIntlLocale(), { month: "short" }).format(date);
}

/**
 * Заголовок дня для разделителя в таблице операций — как в банковской
 * выписке: «сегодня», «вчера» или «6 августа, среда».
 *
 * Относительные подписи только для сегодня и вчера: «3 дня назад» читатель
 * всё равно переводит в дату в уме, и на длинном списке такие подписи
 * мешают больше, чем помогают.
 */
export function formatDayHeading(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.round((date.getTime() - today.getTime()) / 86_400_000);

  if (diffDays === 0) return t("common.today");
  if (diffDays === -1) return t("common.yesterday");

  const formatted = new Intl.DateTimeFormat(getIntlLocale(), {
    day: "numeric",
    month: "long",
    weekday: "short",
    // Год показывается только у прошлых лет: в текущем он лишний шум.
    year: date.getFullYear() === today.getFullYear() ? undefined : "numeric",
  }).format(date);
  return formatted;
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
