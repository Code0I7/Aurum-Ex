import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { RoiYear } from "@/lib/roi";

interface Props {
  rows: RoiYear[];
}

/**
 * Проекция по годам: сколько внесено руками и сколько наросло сверху.
 *
 * Разделение — главное, ради чего график вообще нужен. Одна сплошная кривая
 * роста выглядит убедительно, но не отвечает на вопрос, откуда взялась
 * сумма: если откладывать по тридцать тысяч в месяц, за десять лет
 * наберётся три с половиной миллиона и без всякой доходности. Здесь нижняя
 * область — внесённое, верхняя — заработанное, и видно, какая часть чего.
 */
export function RoiProjectionCard({ rows }: Props) {
  const { t } = useTranslation();

  const data = rows.map((row) => ({
    year: row.year,
    contributed: Math.round(row.contributed),
    earned: Math.round(Math.max(0, row.total - row.contributed)),
  }));

  // Каждый год, пока горизонт короткий. Прореживание по пятилеткам стояло
  // на любом горизонте, и на пяти годах таблица показывала первый, пятый и
  // всё — то есть ровно то, что и так видно по краям графика, а середина
  // пропадала.
  //
  // Дальше десяти лет читать построчно нечего: тридцать строк никто не
  // разглядывает, а опорные точки — разглядывают. Первый и последний год
  // остаются всегда: с них начинают и на них смотрят.
  const EVERY_YEAR_UP_TO = 10;
  const milestones =
    rows.length <= EVERY_YEAR_UP_TO
      ? rows
      : rows.filter((row, index) => index === 0 || row.year % 5 === 0 || index === rows.length - 1);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("roi.projectionTitle")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="var(--gridline)" vertical={false} />
              <XAxis
                dataKey="year"
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: "var(--gridline)" }}
                tickFormatter={(value: number) => t("roi.yearShort", { year: value })}
              />
              <YAxis
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                width={56}
                tickFormatter={(value: number) => `${Math.round(value / 1000)}k`}
              />
              <Tooltip
                isAnimationActive={false}
                contentStyle={{
                  background: "var(--surface-1)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  color: "var(--text-primary)",
                }}
                labelFormatter={(value) => t("roi.yearShort", { year: Number(value) })}
                formatter={(value, key) => [
                  formatCurrency(Number(value ?? 0)),
                  key === "contributed" ? t("roi.contributedTotal") : t("roi.earnedTotal"),
                ]}
              />
              <Legend
                formatter={(value) => (value === "contributed" ? t("roi.contributedTotal") : t("roi.earnedTotal"))}
                wrapperStyle={{ fontSize: 12, color: "var(--text-muted)" }}
              />
              {/* Области складываются: вместе они дают итог, а по отдельности
                  показывают, чем он набран. */}
              <Area
                type="monotone"
                dataKey="contributed"
                stackId="total"
                stroke="var(--series-2)"
                fill="var(--series-2)"
                fillOpacity={0.25}
              />
              <Area
                type="monotone"
                dataKey="earned"
                stackId="total"
                stroke="var(--series-1)"
                fill="var(--series-1)"
                fillOpacity={0.35}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-max border-collapse text-sm">
            <thead>
              <tr className="border-b border-gridline text-left">
                <th className="px-3 py-2 text-xs font-medium uppercase tracking-wide text-text-muted">
                  {t("roi.tableYear")}
                </th>
                <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-text-muted">
                  {t("roi.contributedTotal")}
                </th>
                <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-text-muted">
                  {t("roi.tablePayouts")}
                </th>
                <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-text-muted">
                  {t("roi.tableTotal")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gridline">
              {milestones.map((row) => (
                <tr key={row.year}>
                  <td className="px-3 py-2 tabular-nums text-text-primary">
                    {t("roi.yearShort", { year: row.year })}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-text-muted">
                    {formatCurrency(row.contributed)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-text-muted">
                    {formatCurrency(row.payoutsTotal)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums font-medium text-text-primary">
                    {formatCurrency(row.total)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
