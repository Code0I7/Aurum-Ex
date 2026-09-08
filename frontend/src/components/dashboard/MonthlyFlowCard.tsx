import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useTranslation, getLanguage } from "@/lib/i18n";
import { formatCurrency, formatSignedCurrency, getMonthLabels } from "@/lib/format";
import type { DashboardMonthPoint } from "@/types";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { BAR_CURSOR } from "@/components/charts/cursors";

/**
 * Движение денег по месяцам внутри выбранного периода.
 *
 * Считается тем же расчётом, что и страница «Движение денег»: два разных
 * ответа на один вопрос — худшее, что приложение может показать про деньги.
 *
 * За один месяц не рисуется: столбик из одного значения не показывает
 * динамику, ради которой график и нужен.
 */
export function MonthlyFlowCard({ points }: { points: DashboardMonthPoint[] }) {
  const { t } = useTranslation();
  const months = getMonthLabels(getLanguage());

  if (points.length < 2) return null;

  const data = points.map((point) => ({
    label: `${months[point.month - 1].slice(0, 3)} ${String(point.year).slice(2)}`,
    income: Number(point.income),
    // Расход рисуется вниз: столбцы навстречу друг другу читаются как
    // «пришло / ушло» без легенды.
    expense: -Number(point.expense),
    net: Number(point.net),
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("dashboard.monthlyTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-52 w-full sm:h-60">
          <div className="chart-palette h-full w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }} stackOffset="sign">
              <CartesianGrid stroke="var(--gridline)" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                stroke="var(--gridline)"
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                stroke="var(--gridline)"
                width={64}
                tickFormatter={(value: number) => formatCurrency(Math.abs(value))}
              />
              <Tooltip
                isAnimationActive={false}
                cursor={BAR_CURSOR}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const point = payload[0].payload as (typeof data)[number];
                  return (
                    <ChartTooltipBox className="text-xs">
                      <p className="text-text-muted">{point.label}</p>
                      <p className="text-success">
                        {t("cashFlow.income")}: {formatCurrency(point.income)}
                      </p>
                      <p className="text-danger">
                        {t("cashFlow.expense")}: {formatCurrency(Math.abs(point.expense))}
                      </p>
                      <p className="font-medium text-text-primary">
                        {t("cashFlow.net")}: {formatSignedCurrency(point.net)}
                      </p>
                    </ChartTooltipBox>
                  );
                }}
              />
              <Bar dataKey="income" fill="var(--success)" radius={[2, 2, 0, 0]} />
              <Bar dataKey="expense" fill="var(--danger)" radius={[0, 0, 2, 2]} />
            </BarChart>
          </ResponsiveContainer>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
