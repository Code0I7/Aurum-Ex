import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { formatCurrency, getIntlLocale, pluralizeRu } from "@/lib/format";
import { formatMonthShort } from "@/lib/format";
import { useTranslation, type Language } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { CategorySpendingReport } from "@/types";

interface CategorySpendingChartProps {
  report: CategorySpendingReport | undefined;
  isLoading: boolean;
}

function monthKey(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

function formatMonthLabel(key: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { month: "short", year: "numeric" }).format(
    new Date(`${key}T00:00:00`)
  );
}

function transactionsCountLabel(count: number, language: Language): string {
  if (language === "ru") return pluralizeRu(count, "транзакция", "транзакции", "транзакций");
  return count === 1 ? "transaction" : "transactions";
}

/**
 * Подписи оси: годы на длинном отрезке и месяцы на коротком.
 *
 * Одними годами обходиться нельзя. На отчёте за один год отметок не
 * оставалось вовсе, и столбцы висели без единой подписи — понять, где март,
 * а где ноябрь, было не по чему. Поэтому: отрезок в пределах одного года
 * подписывается месяцами, длиннее — годами, иначе подписи слипаются.
 */
function computeAxisTicks(keys: string[]): { ticks: string[]; kind: "year" | "month" } {
  if (keys.length < 2) return { ticks: [], kind: "month" };
  const startYear = Number(keys[0].slice(0, 4));
  const endYear = Number(keys[keys.length - 1].slice(0, 4));

  if (startYear === endYear) {
    // Первый день каждого месяца, который реально есть в данных.
    const seen = new Set<string>();
    const ticks = keys.filter((key) => {
      const month = key.slice(0, 7);
      if (seen.has(month)) return false;
      seen.add(month);
      return true;
    });
    return { ticks, kind: "month" };
  }

  const ticks: string[] = [];
  for (let year = startYear + 1; year <= endYear; year++) {
    const jan = `${year}-01-01`;
    if (keys.includes(jan)) ticks.push(jan);
  }
  return { ticks, kind: "year" };
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: { key: string; amount: number } }> }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm shadow-md">
      <p className="text-text-muted">{formatMonthLabel(point.key)}</p>
      <p className="font-medium text-text-primary">{formatCurrency(point.amount)}</p>
    </div>
  );
}

export function CategorySpendingChart({ report, isLoading }: CategorySpendingChartProps) {
  const { t, language } = useTranslation();
  const chartData = report?.series.map((point) => ({
    key: monthKey(point.year, point.month),
    amount: Number(point.amount),
  })) ?? [];
  const axis = computeAxisTicks(chartData.map((point) => point.key));

  return (
    <Card>
      <CardHeader className="items-start">
        <div>
          <CardTitle>{report ? translateCategoryName(report.category_name) : t("reports.defaultChartTitle")}</CardTitle>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums text-text-primary sm:text-[28px]">
            {isLoading || !report ? "…" : formatCurrency(report.total_amount)}
          </p>
          {report && (
            <p className="mt-1 text-sm text-text-muted">
              {t("reports.averagePerMonth", { amount: formatCurrency(report.average_per_month) })} ·{" "}
              {report.transaction_count} {transactionsCountLabel(report.transaction_count, language)}
            </p>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-56 w-full sm:h-64">
          {isLoading || !report || chartData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-text-muted">
              {isLoading ? t("common.loading") : t("reports.noDataForPeriod")}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
                {axis.ticks.length > 0 && (
                  <XAxis
                    dataKey="key"
                    type="category"
                    ticks={axis.ticks}
                    tickFormatter={(value: string) =>
                      axis.kind === "year" ? value.slice(0, 4) : formatMonthShort(value)
                    }
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                    interval="preserveStartEnd"
                  />
                )}
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--surface-2)" }} />
                <Bar dataKey="amount" fill={report.category_color} radius={[2, 2, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        {chartData.length > 1 && (
          <div className="mt-2 flex justify-between text-xs text-text-muted">
            <span>{formatMonthLabel(chartData[0].key)}</span>
            <span>{formatMonthLabel(chartData[chartData.length - 1].key)}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
