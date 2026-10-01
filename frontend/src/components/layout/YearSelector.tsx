import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { CustomDateRange } from "@/lib/dateRange";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface YearDropdownProps {
  years: number[];
  year: number;
  onChange: (year: number) => void;
}

/** Compact single-year dropdown, most recent year first. Shared building
 * block behind YearSelector below. */
function YearDropdown({ years, year, onChange }: YearDropdownProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const sortedYears = [...years].sort((a, b) => b - a);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex h-9 items-center gap-1.5 rounded-lg border border-border bg-surface-1 px-3 text-sm font-medium text-text-primary transition-colors hover:bg-surface-2"
      >
        {year}
        <ChevronDown size={14} className={cn("text-text-muted transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute right-0 top-full z-20 mt-1.5 max-h-64 w-24 overflow-y-auto rounded-lg border border-border bg-surface-1 py-1 shadow-lg"
        >
          {sortedYears.map((value) => {
            const active = value === year;
            return (
              <li key={value}>
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    onChange(value);
                    setOpen(false);
                  }}
                  className={cn(
                    "block w-full px-3 py-1.5 text-left text-sm transition-colors",
                    active ? "bg-surface-2 font-semibold text-text-primary" : "text-text-secondary hover:bg-surface-2"
                  )}
                >
                  {value}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Sits to the right of MonthSelector instead of competing with it as a
 * second row of pills. */
export function YearSelector(props: YearDropdownProps) {
  return <YearDropdown {...props} />;
}

interface DateRangeSelectorProps {
  /** Годы, в которых есть записи. Нужны не для выбора, а для границ: дальше
   *  них данных нет, и предлагать 1998-й незачем. */
  years: number[];
  value: CustomDateRange;
  onChange: (range: CustomDateRange) => void;
}

/**
 * Свой период двумя датами — для пресета «свой» на страницах капитала,
 * движения денег и отчётов.
 *
 * Раньше здесь стояли два списка лет, и срез за март–май 2024 выразить было
 * нечем. Пресеты рядом никуда не делись: «этот год» и «пять лет» отвечают
 * на частые вопросы одним щелчком, а даты нужны там, где вопрос редкий.
 *
 * Границы не дают уйти туда, где записей нет, а порядок сохраняется
 * подтягиванием второй даты, а не отказом: перевёрнутый период — это не
 * выбор, а опечатка, и чинить её молча лучше, чем спорить с человеком.
 */
export function DateRangeSelector({ years, value, onChange }: DateRangeSelectorProps) {
  const { t } = useTranslation();
  const known = years.length > 0 ? years : [new Date().getFullYear()];
  const min = `${Math.min(...known)}-01-01`;
  const max = `${Math.max(...known, new Date().getFullYear())}-12-31`;

  const field =
    "h-9 shrink-0 rounded-lg border border-border bg-surface-1 px-2 text-sm text-text-primary transition-colors hover:bg-surface-2";

  return (
    <div className="flex shrink-0 items-center gap-1.5">
      <input
        type="date"
        value={value.from}
        min={min}
        max={max}
        aria-label={t("reports.rangeFrom")}
        onChange={(event) =>
          onChange({ from: event.target.value, to: laterOf(value.to, event.target.value) })
        }
        className={field}
      />
      <span className="text-sm text-text-muted">–</span>
      <input
        type="date"
        value={value.to}
        min={min}
        max={max}
        aria-label={t("reports.rangeTo")}
        onChange={(event) =>
          onChange({ from: earlierOf(value.from, event.target.value), to: event.target.value })
        }
        className={field}
      />
    </div>
  );
}

/** Сравнение «ГГГГ-ММ-ДД» строками: формат с фиксированной шириной, и
 *  лексикографический порядок у него совпадает с хронологическим. */
function laterOf(a: string, b: string): string {
  return a >= b ? a : b;
}

function earlierOf(a: string, b: string): string {
  return a <= b ? a : b;
}
