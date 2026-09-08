import { useState } from "react";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency, getMonthLabels } from "@/lib/format";
import { getLanguage } from "@/lib/i18n";
import type { PlanMonthCell, PlanOverview, PlanRow } from "@/types";

interface PlanTableProps {
  overview: PlanOverview;
}

type Mode = "planned" | "actual" | "deviation";

/**
 * Год целиком: категории по строкам, месяцы по столбцам.
 *
 * В исходной таблице на каждый месяц приходилось пять колонок — план,
 * процент от дохода, факт, процент, отклонение, — и лист уезжал вправо на
 * шестьдесят столбцов. Здесь показывается одна величина за раз, а
 * переключатель наверху решает какая: три числа в одной клетке всё равно
 * невозможно прочесть, а разница между ними — это и есть третий режим.
 */
export function PlanTable({ overview }: PlanTableProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>("planned");
  const months = getMonthLabels(getLanguage());

  const modes: Array<{ key: Mode; label: string }> = [
    { key: "planned", label: t("planning.planned") },
    { key: "actual", label: t("planning.actual") },
    { key: "deviation", label: t("planning.deviation") },
  ];

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1">
        {modes.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setMode(item.key)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium ${
              mode === item.key
                ? "bg-surface-2 text-text-primary"
                : "text-text-muted hover:bg-surface-2 hover:text-text-primary"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Двенадцать месяцев не помещаются на телефон ни при каком раскладе,
          поэтому таблица прокручивается вбок, а колонка с названием
          категории прибита к левому краю — иначе, докрутив до декабря, не
          понять, чья это строка. */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] border-separate border-spacing-0 text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-wide text-text-muted">
              <th className="sticky left-0 z-10 bg-surface-1 py-2 pr-3 text-left font-medium">
                {t("planning.category")}
              </th>
              {months.map((label) => (
                <th key={label} className="px-2 py-2 text-right font-medium">
                  {label.slice(0, 3)}
                </th>
              ))}
              <th className="py-2 pl-3 text-right font-medium">{t("planning.year")}</th>
            </tr>
          </thead>
          <tbody>
            {overview.rows.map((row) => (
              <BodyRow key={`${row.category_id ?? "none"}-${row.name}`} row={row} mode={mode} />
            ))}
          </tbody>
          <tfoot>
            <TotalsRow label={t("planning.incomeTotal")} cells={overview.income_totals} mode={mode} />
            <TotalsRow label={t("planning.expenseTotal")} cells={overview.expense_totals} mode={mode} />
            {/* Свободные средства — то, ради чего вся таблица: сколько
                осталось бы, если бы всё шло по плану, и сколько осталось. */}
            <TotalsRow label={t("planning.free")} cells={overview.free_totals} mode={mode} emphasis />
          </tfoot>
        </table>
      </div>
    </div>
  );
}

function valueOf(cell: PlanMonthCell, mode: Mode): number {
  if (mode === "planned") return Number(cell.planned);
  if (mode === "actual") return Number(cell.actual);
  return Number(cell.deviation);
}

function BodyRow({ row, mode }: { row: PlanRow; mode: Mode }) {
  const total =
    mode === "planned"
      ? Number(row.planned_total)
      : mode === "actual"
        ? Number(row.actual_total)
        : Number(row.actual_total) - Number(row.planned_total);

  return (
    <tr className="border-b border-border/40">
      <th className="sticky left-0 z-10 truncate bg-surface-1 py-2 pr-3 text-left font-normal">{row.name}</th>
      {row.months.map((cell) => (
        <Cell key={cell.month} value={valueOf(cell, mode)} mode={mode} isIncome={row.kind === "income"} />
      ))}
      <Cell value={total} mode={mode} isIncome={row.kind === "income"} strong />
    </tr>
  );
}

function TotalsRow({
  label,
  cells,
  mode,
  emphasis,
}: {
  label: string;
  cells: PlanMonthCell[];
  mode: Mode;
  emphasis?: boolean;
}) {
  const total = cells.reduce((sum, cell) => sum + valueOf(cell, mode), 0);
  // Итоговые полосы всегда читаются «по-доходному»: больше — лучше. Для
  // расходов это верно тоже: перерасход показывается в строке свободных
  // средств тем же минусом.
  return (
    <tr className={emphasis ? "border-t-2 border-border" : "border-t border-border/60"}>
      <th
        className={`sticky left-0 z-10 bg-surface-1 py-2 pr-3 text-left ${
          emphasis ? "font-semibold" : "font-medium"
        }`}
      >
        {label}
      </th>
      {cells.map((cell) => (
        <Cell key={cell.month} value={valueOf(cell, mode)} mode={mode} isIncome strong={emphasis} />
      ))}
      <Cell value={total} mode={mode} isIncome strong />
    </tr>
  );
}

/**
 * Клетка. Цветом красится только режим отклонения: в режимах «план» и
 * «факт» цвет означал бы, что сумма сама по себе хорошая или плохая, а это
 * неправда — 40 000 расхода при 45 000 дохода нормальны.
 */
function Cell({
  value,
  mode,
  isIncome,
  strong,
}: {
  value: number;
  mode: Mode;
  isIncome: boolean;
  strong?: boolean;
}) {
  let color = "text-text-secondary";
  if (mode === "deviation" && value !== 0) {
    // Для дохода плюс — хорошо, для расхода плюс — перерасход. Знак один и
    // тот же, смысл противоположный, поэтому цвет зависит от вида строки.
    const good = isIncome ? value > 0 : value < 0;
    color = good ? "text-success" : "text-danger";
  }

  return (
    <td
      className={`px-2 py-2 text-right tabular-nums ${color} ${strong ? "font-semibold" : ""}`}
      // Ноль намеренно прочерк: пустая клетка читается быстрее, чем поле
      // нулей, а «плана не было» и «план ноль» — одно и то же.
    >
      {value === 0 ? <span className="text-text-muted">—</span> : formatCurrency(value)}
    </td>
  );
}
