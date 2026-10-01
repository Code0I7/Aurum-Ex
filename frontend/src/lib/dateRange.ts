/** Shared by CashFlowPage and ReportsPage — both offer the same four
 * period presets over their respective date-ranged endpoints. */
export type RangePreset = "all" | "this_year" | "5y" | "custom";

/**
 * Свой период — две даты, а не два года.
 *
 * Годами он был потому, что выбор рисовался двумя списками лет, и срез за
 * март–май 2024 выразить было нечем: любой выбор разворачивался в целые
 * годы. Сервер при этом всегда принимал произвольные даты — ограничение
 * жило только здесь.
 */
export interface CustomDateRange {
  /** «ГГГГ-ММ-ДД», включительно. */
  from: string;
  /** «ГГГГ-ММ-ДД», включительно. */
  to: string;
}

/** Дата в виде «ГГГГ-ММ-ДД» по местному времени.
 *
 * Не через toISOString: тот переводит в UTC, и восточнее Гринвича ранним
 * утром возвращал вчерашний день — «по сегодня» молча теряло операции
 * сегодняшнего дня. */
function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Период по умолчанию для «своего»: с начала года по сегодня.
 *
 * Не по тридцать первое декабря: большую часть года это дата из будущего, а
 * период, который кончается позже сегодняшнего дня, обещает данные, которых
 * ещё нет. */
export function defaultCustomRange(today: Date = new Date()): CustomDateRange {
  return { from: `${today.getFullYear()}-01-01`, to: isoDate(today) };
}

export function computeRange(
  preset: RangePreset,
  custom?: CustomDateRange
): { startDate?: string; endDate?: string } {
  const today = new Date();
  switch (preset) {
    case "all":
      return {};
    case "this_year":
      return { startDate: `${today.getFullYear()}-01-01`, endDate: isoDate(today) };
    case "5y": {
      const start = new Date(today.getFullYear() - 5, today.getMonth(), 1);
      return { startDate: isoDate(start), endDate: isoDate(today) };
    }
    case "custom": {
      if (!custom) return {};
      return { startDate: custom.from, endDate: custom.to };
    }
  }
}
