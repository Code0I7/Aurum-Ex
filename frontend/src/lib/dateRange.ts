/** Shared by CashFlowPage and ReportsPage — both offer the same four
 * period presets over their respective date-ranged endpoints. */
export type RangePreset = "all" | "this_year" | "5y" | "custom";

export interface CustomYearRange {
  fromYear: number;
  toYear: number;
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

export function computeRange(
  preset: RangePreset,
  custom?: CustomYearRange
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
      return { startDate: `${custom.fromYear}-01-01`, endDate: `${custom.toYear}-12-31` };
    }
  }
}
