import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { formatCurrency, formatSignedCurrency, getIntlLocale } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CashFlowResponse } from "@/types";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { BAR_CURSOR } from "@/components/charts/cursors";

interface CashFlowChartProps {
  cashFlow: CashFlowResponse | undefined;
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

/** Same landmark idea as the Net Worth and category-spending charts: year
 * ticks only when the bars span more than one calendar year. */
function computeYearTicks(keys: string[]): string[] {
  if (keys.length < 2) return [];
  const startYear = Number(keys[0].slice(0, 4));
  const endYear = Number(keys[keys.length - 1].slice(0, 4));
  if (startYear === endYear) return [];
  const ticks: string[] = [];
  for (let year = startYear + 1; year <= endYear; year++) {
    const jan = `${year}-01-01`;
    if (keys.includes(jan)) ticks.push(jan);
  }
  return ticks;
}

interface ChartPoint {
  key: string;
  income: number;
  expense: number;
  net: number;
  // Начальный остаток счетов, открытых в этом месяце. Уже входит в income.
  opening: number;
}

function ChartTooltip({
  active,
  payload,
  incomeLabel,
  expenseLabel,
  netLabel,
  openingLabel,
}: {
  active?: boolean;
  payload?: Array<{ payload: ChartPoint }>;
  incomeLabel: string;
  expenseLabel: string;
  netLabel: string;
  openingLabel: string;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <ChartTooltipBox>
      <p className="text-text-muted">{formatMonthLabel(point.key)}</p>
      <p className="text-success">
        {incomeLabel}: {formatCurrency(point.income)}
      </p>
      <p className="text-danger">
        {expenseLabel}: {formatCurrency(point.expense)}
      </p>
      <p className="font-medium text-text-primary">
        {netLabel}: {formatSignedCurrency(point.net)}
      </p>
      {/* Начальный остаток уже сложен в доход. Подписывается отдельно, иначе
          столбец в месяце открытия счёта выглядит необъяснимым всплеском. */}
      {point.opening !== 0 && (
        <p className="mt-1 text-xs text-text-muted">
          {openingLabel}: {formatSignedCurrency(point.opening)}
        </p>
      )}
    </ChartTooltipBox>
  );
}

export function CashFlowChart({ cashFlow, isLoading }: CashFlowChartProps) {
  const { t } = useTranslation();
  const incomeLabel = t("cashFlow.income");
  const expenseLabel = t("cashFlow.expense");
  const netLabel = t("cashFlow.net");
  const openingLabel = t("cashFlow.opening");

  const chartData: ChartPoint[] =
    cashFlow?.points.map((point) => ({
      key: monthKey(point.year, point.month),
      income: Number(point.income),
      expense: Number(point.expense),
      net: Number(point.net),
      opening: Number(point.opening),
    })) ?? [];
  const yearTicks = computeYearTicks(chartData.map((point) => point.key));

  return (
    <Card>
      <CardHeader className="items-start">
        <div>
          <CardTitle>{t("nav.cashFlow")}</CardTitle>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums text-text-primary sm:text-[28px]">
            {isLoading || !cashFlow ? "…" : formatSignedCurrency(cashFlow.total_net)}
          </p>
          {cashFlow && (
            <p className="mt-1 text-sm">
              <span className="font-medium text-success">
                {incomeLabel} {formatCurrency(cashFlow.total_income)}
              </span>
              <span className="text-text-muted"> · </span>
              <span className="font-medium text-danger">
                {expenseLabel} {formatCurrency(cashFlow.total_expense)}
              </span>
            </p>
          )}
          {/* Начальные остатки заработаны до начала учёта. В обороте они
              участвуют — иначе сальдо не сойдётся с остатком на счетах, — но
              приписывать их периоду молча нечестно. */}
          {cashFlow && Number(cashFlow.total_opening) !== 0 && (
            <p className="mt-1 text-xs text-text-muted">
              {t("cashFlow.openingHint", {
                amount: formatSignedCurrency(cashFlow.total_opening),
              })}
            </p>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-56 w-full sm:h-64">
          {isLoading || !cashFlow || chartData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-text-muted">
              {isLoading ? t("common.loading") : t("cashFlow.noData")}
            </div>
          ) : (
            <div className="chart-palette h-full w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
                {yearTicks.length > 0 && (
                  <XAxis
                    dataKey="key"
                    type="category"
                    ticks={yearTicks}
                    tickFormatter={(value: string) => value.slice(0, 4)}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                    interval="preserveStartEnd"
                  />
                )}
                <Tooltip
                  isAnimationActive={false}
                  content={
                    <ChartTooltip
                      incomeLabel={incomeLabel}
                      expenseLabel={expenseLabel}
                      netLabel={netLabel}
                      openingLabel={openingLabel}
                    />
                  }
                  cursor={BAR_CURSOR}
                />
                <Legend
                  verticalAlign="top"
                  height={24}
                  formatter={(value) => (value === "income" ? incomeLabel : expenseLabel)}
                  wrapperStyle={{ fontSize: 12, color: "var(--text-muted)" }}
                />
                <Bar dataKey="income" fill="var(--success)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="expense" fill="var(--danger)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
            </div>
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
