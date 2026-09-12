/**
 * Расписание плана: правило, пресеты и подпись к ним словами.
 *
 * Правило состоит из частоты, шага и уточнений, и глядя на семь полей формы
 * человек не может сказать, что получилось. Поэтому под формой стоит одна
 * строка — «Каждые 2 недели: по понедельникам», — и собирается она здесь:
 * подпись обязана быть той же самой везде, где правило показывают, иначе
 * список планов и форма начнут расходиться в словах об одном и том же.
 *
 * Морфология живёт тут, а не в словаре i18n: там плоские строки, а «в
 * первый понедельник», но «в первую среду» — это согласование по роду, и
 * разложить его по ключам значило бы завести их несколько сотен.
 */
import type { Language } from "@/lib/i18n";
import { ordinalEn, pluralEn, pluralRu } from "@/lib/plural";
import type { PlanFrequency, PlanMonthDayMode } from "@/types";

/** Та часть плана, что отвечает на вопрос «когда», без сумм и категорий. */
export interface Recurrence {
  kind: PlanFrequency;
  repeat_every: number;
  weekdays: number[] | null;
  month_day_mode: PlanMonthDayMode | null;
  month_days: number[] | null;
  nth_weekday: number | null;
  months: number[] | null;
  skip_weekends: boolean;
  workdays_only: boolean;
}

/**
 * Готовый вариант из списка «Повторение».
 *
 * Пресет — это не отдельное правило, а то же самое правило с шагом единица:
 * «еженедельно» и «каждые 3 недели» отличаются одним числом. Хранить пресет
 * в базе поэтому нечего — он вычисляется из правила и нужен только форме,
 * чтобы открыться на том пункте, который человек выбирал.
 */
export type RecurrencePreset =
  | "once"
  | "daily"
  | "workday"
  | "weekly"
  | "monthly"
  | "yearly"
  | "custom";

export const PRESETS: RecurrencePreset[] = [
  "once",
  "daily",
  "workday",
  "weekly",
  "monthly",
  "yearly",
  "custom",
];

/** Правило по умолчанию — ежемесячное: так заведено большинство планов. */
export const DEFAULT_RECURRENCE: Recurrence = {
  kind: "month",
  repeat_every: 1,
  weekdays: null,
  month_day_mode: null,
  month_days: null,
  nth_weekday: null,
  months: null,
  skip_weekends: false,
  workdays_only: false,
};

/** На каком пункте списка открыть форму для уже сохранённого правила. */
export function presetOf(rule: Recurrence): RecurrencePreset {
  if (rule.kind === "one_off") return "once";
  if (rule.repeat_every !== 1) return "custom";
  if (rule.kind === "day") return rule.skip_weekends ? "workday" : "daily";
  if (rule.kind === "week") return "weekly";
  if (rule.kind === "month") return "monthly";
  return "yearly";
}

/**
 * Правило, которое получается при выборе пункта списка.
 *
 * Уточнения не переносятся между пунктами: дни недели, выбранные для
 * «еженедельно», в «ежемесячно» ничего не значат, и сервер такой план не
 * примет. Сбрасывать их молча здесь честнее, чем показать человеку ошибку
 * сохранения про поле, которого он уже не видит.
 */
export function recurrenceOfPreset(preset: RecurrencePreset, previous: Recurrence): Recurrence {
  const base: Recurrence = { ...DEFAULT_RECURRENCE };
  switch (preset) {
    case "once":
      return { ...base, kind: "one_off" };
    case "daily":
      // Единственная галочка, которая переживает смену пункта: «по
      // отработанным дням» — это про тот же самый ежедневный план.
      return { ...base, kind: "day", workdays_only: previous.workdays_only };
    case "workday":
      return { ...base, kind: "day", skip_weekends: true };
    case "weekly":
      return { ...base, kind: "week", weekdays: previous.weekdays };
    case "monthly":
      return { ...base, kind: "month" };
    case "yearly":
      return { ...base, kind: "year" };
    case "custom":
      // «Произвольно» — это то же правило с шагом, который человек сейчас
      // напечатает: терять уже выбранное при переходе сюда незачем.
      return { ...previous, kind: previous.kind === "one_off" ? "month" : previous.kind };
  }
}

// Дни недели: 0 — понедельник, как в Python и в самом правиле.
const RU_WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const EN_WEEKDAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
// «По понедельникам» — дательный падеж множественного числа.
const RU_WEEKDAYS_DATIVE = [
  "понедельникам",
  "вторникам",
  "средам",
  "четвергам",
  "пятницам",
  "субботам",
  "воскресеньям",
];
// «В первый понедельник», «в первую среду» — винительный единственного.
const RU_WEEKDAYS_ACCUSATIVE = [
  "понедельник",
  "вторник",
  "среду",
  "четверг",
  "пятницу",
  "субботу",
  "воскресенье",
];
// Род дня недели: 0 — мужской, 1 — женский, 2 — средний. Нужен порядковому
// числительному перед ним: «первый понедельник», но «первую среду».
const RU_WEEKDAY_GENDER = [0, 0, 1, 0, 1, 1, 2];
const RU_ORDINALS: string[][] = [
  ["первый", "первую", "первое"],
  ["второй", "вторую", "второе"],
  ["третий", "третью", "третье"],
  ["четвёртый", "четвёртую", "четвёртое"],
  ["пятый", "пятую", "пятое"],
];
const RU_LAST = ["последний", "последнюю", "последнее"];
const EN_ORDINALS = ["first", "second", "third", "fourth", "fifth"];
// «В октябре» — предложный падеж: месяцы в подписи стоят после предлога.
const RU_MONTHS_PREPOSITIONAL = [
  "январе",
  "феврале",
  "марте",
  "апреле",
  "мае",
  "июне",
  "июле",
  "августе",
  "сентябре",
  "октябре",
  "ноябре",
  "декабре",
];
const EN_MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/**
 * Единица шага для списка рядом с числом: «2 недели», «5 недель».
 *
 * Именительный падеж, в отличие от подписи целиком: там «каждые 2 недели» —
 * часть предложения, здесь — пункт списка сам по себе.
 */
export function stepUnitLabel(kind: PlanFrequency, count: number, language: Language): string {
  if (language === "ru") {
    if (kind === "day") return pluralRu(count, ["день", "дня", "дней"]);
    if (kind === "week") return pluralRu(count, ["неделя", "недели", "недель"]);
    if (kind === "month") return pluralRu(count, ["месяц", "месяца", "месяцев"]);
    return pluralRu(count, ["год", "года", "лет"]);
  }
  if (kind === "day") return pluralEn(count, "day", "days");
  if (kind === "week") return pluralEn(count, "week", "weeks");
  if (kind === "month") return pluralEn(count, "month", "months");
  return pluralEn(count, "year", "years");
}

/** Короткие подписи для кнопок выбора дней недели. */
export function weekdayLabels(language: Language): string[] {
  return language === "ru" ? RU_WEEKDAYS_SHORT : EN_WEEKDAYS_SHORT;
}

/** «Первый», «последний» и всё между ними — для выбора номера дня недели. */
export function nthLabels(language: Language, weekday: number): { value: number; label: string }[] {
  const gender = RU_WEEKDAY_GENDER[weekday] ?? 0;
  const numbers = [1, 2, 3, 4, 5];
  if (language === "ru") {
    return [
      ...numbers.map((value) => ({ value, label: RU_ORDINALS[value - 1][gender] })),
      { value: -1, label: RU_LAST[gender] },
    ];
  }
  return [
    ...numbers.map((value) => ({ value, label: EN_ORDINALS[value - 1] })),
    { value: -1, label: "last" },
  ];
}

/** Перечисление через запятую с союзом перед последним: «1-го, 5-го и 20-го». */
function joinList(parts: string[], conjunction: string): string {
  if (parts.length <= 1) return parts.join("");
  return `${parts.slice(0, -1).join(", ")} ${conjunction} ${parts[parts.length - 1]}`;
}

/** Часть подписи про день внутри месяца — общая у месячного и годового. */
function describeMonthDay(rule: Recurrence, language: Language): string {
  const ru = language === "ru";
  switch (rule.month_day_mode) {
    case "day_of_month": {
      const days = [...(rule.month_days ?? [])].sort((left, right) => left - right);
      if (days.length === 0) return "";
      return ru
        ? joinList(
            days.map((day) => `${day}-го`),
            "и"
          )
        : `on the ${joinList(days.map(ordinalEn), "and")}`;
    }
    case "nth_weekday": {
      const nth = rule.nth_weekday ?? 1;
      const days = [...(rule.weekdays ?? [])].sort((left, right) => left - right);
      if (days.length === 0) return "";
      const named = days.map((weekday) => {
        if (ru) {
          const gender = RU_WEEKDAY_GENDER[weekday] ?? 0;
          const ordinal = nth === -1 ? RU_LAST[gender] : RU_ORDINALS[nth - 1][gender];
          return `${ordinal} ${RU_WEEKDAYS_ACCUSATIVE[weekday]}`;
        }
        const ordinal = nth === -1 ? "last" : EN_ORDINALS[nth - 1];
        return `${ordinal} ${EN_WEEKDAYS_SHORT[weekday]}`;
      });
      return ru ? `в ${joinList(named, "и")}` : `on the ${joinList(named, "and")}`;
    }
    case "last_day":
      return ru ? "в последний день месяца" : "on the last day";
    case "first_workday":
      return ru ? "в первый рабочий день" : "on the first workday";
    case "last_workday":
      return ru ? "в последний рабочий день" : "on the last workday";
    default:
      // Число не важно — повторение стоит на том же числе, с которого план
      // начался, и называть его подписи нечем: даты здесь ещё нет.
      return "";
  }
}

/**
 * Правило одной строкой: «Каждые 2 недели: по понедельникам и средам».
 *
 * Это единственное место, где расписание превращается в слова, — и форма, и
 * список планов зовут его, чтобы человек читал об одном и том же одинаково.
 */
export function describeRecurrence(rule: Recurrence, language: Language): string {
  const ru = language === "ru";
  const step = Math.max(rule.repeat_every || 1, 1);

  if (rule.kind === "one_off") return ru ? "Один раз" : "Once";

  if (rule.kind === "day") {
    if (rule.workdays_only) {
      return ru ? "Каждый отработанный день" : "Every day worked";
    }
    if (step === 1) {
      if (rule.skip_weekends) return ru ? "Каждый рабочий день" : "Every workday";
      return ru ? "Каждый день" : "Every day";
    }
    const head = ru
      ? `Каждые ${step} ${pluralRu(step, ["день", "дня", "дней"])}`
      : `Every ${step} ${pluralEn(step, "day", "days")}`;
    if (!rule.skip_weekends) return head;
    return ru ? `${head}, пропуская выходные` : `${head}, skipping weekends`;
  }

  if (rule.kind === "week") {
    const head =
      step === 1
        ? ru
          ? "Каждую неделю"
          : "Every week"
        : ru
          ? `Каждые ${step} ${pluralRu(step, ["неделю", "недели", "недель"])}`
          : `Every ${step} ${pluralEn(step, "week", "weeks")}`;
    const days = [...(rule.weekdays ?? [])].sort((left, right) => left - right);
    if (days.length === 0) return head;
    return ru
      ? `${head}: по ${joinList(days.map((day) => RU_WEEKDAYS_DATIVE[day]), "и")}`
      : `${head} on ${joinList(days.map((day) => EN_WEEKDAYS_SHORT[day]), "and")}`;
  }

  if (rule.kind === "month") {
    const head =
      step === 1
        ? ru
          ? "Каждый месяц"
          : "Every month"
        : ru
          ? `Каждые ${step} ${pluralRu(step, ["месяц", "месяца", "месяцев"])}`
          : `Every ${step} ${pluralEn(step, "month", "months")}`;
    const day = describeMonthDay(rule, language);
    return day ? `${head}, ${day}` : head;
  }

  const head =
    step === 1
      ? ru
        ? "Каждый год"
        : "Every year"
      : ru
        ? `Каждые ${step} ${pluralRu(step, ["год", "года", "лет"])}`
        : `Every ${step} ${pluralEn(step, "year", "years")}`;
  const months = [...(rule.months ?? [])].sort((left, right) => left - right);
  const where =
    months.length > 0
      ? ru
        ? ` в ${joinList(months.map((month) => RU_MONTHS_PREPOSITIONAL[month - 1]), "и")}`
        : ` in ${joinList(months.map((month) => EN_MONTHS[month - 1]), "and")}`
      : "";
  const day = describeMonthDay(rule, language);
  return day ? `${head}${where}, ${day}` : `${head}${where}`;
}
