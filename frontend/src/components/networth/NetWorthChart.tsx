import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDown, ArrowUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { RangeSelector } from "@/components/layout/RangeSelector";
import { YearRangeSelector } from "@/components/layout/YearSelector";
import type { CustomYearRange } from "@/lib/dateRange";
import { formatCurrency, formatSignedCurrency, getIntlLocale } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { NetWorthRange, NetWorthSummary } from "@/types";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { LINE_CURSOR } from "@/components/charts/cursors";

interface NetWorthChartProps {
  summary: NetWorthSummary | undefined;
  isLoading: boolean;
  range: NetWorthRange;
  onRangeChange: (range: NetWorthRange) => void;
  // Свой период. Годы для выпадающих списков берутся из истории операций:
  // предлагать 1998-й, когда записи начинаются с 2022-го, незачем.
  years: number[];
  customRange: CustomYearRange;
  onCustomRangeChange: (range: CustomYearRange) => void;
}

function formatAxisDate(iso: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { month: "short", day: "numeric", year: "numeric" }).format(
    new Date(`${iso}T00:00:00`)
  );
}

/** Jan-1 of every year strictly inside the range, so a multi-year chart gets
 * a year landmark on its axis instead of just two endpoint dates — lets you
 * place "5 years ago" without hovering pixel-by-pixel. Single-year ranges
 * return an empty array and the axis stays hidden, unchanged from before. */
function computeYearTicks(dates: string[]): string[] {
  if (dates.length < 2) return [];
  const start = dates[0];
  const end = dates[dates.length - 1];
  const startYear = Number(start.slice(0, 4));
  const endYear = Number(end.slice(0, 4));
  if (startYear === endYear) return [];

  const ticks: string[] = [];
  for (let year = startYear + 1; year <= endYear; year++) {
    const jan1 = `${year}-01-01`;
    if (jan1 >= start && jan1 <= end) ticks.push(jan1);
  }
  return ticks;
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: { date: string; value: number } }> }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <ChartTooltipBox>
      <p className="text-text-muted">{formatAxisDate(point.date)}</p>
      <p className="font-medium text-text-primary">{formatCurrency(point.value)}</p>
    </ChartTooltipBox>
  );
}

export function NetWorthChart({
  summary,
  isLoading,
  range,
  onRangeChange,
  years,
  customRange,
  onCustomRangeChange,
}: NetWorthChartProps) {
  const { t } = useTranslation();
  const isPositive = summary ? Number(summary.change_amount) >= 0 : true;
  const trendColor = isPositive ? "var(--success)" : "var(--danger)";
  // Отрицательный капитал — это долгов больше, чем имущества, и число
  // должно об этом сказать само. Знак минуса в общем ряду цифр теряется,
  // а цвет виден раньше, чем прочитана сумма.
  const isUnderwater = summary ? Number(summary.current) < 0 : false;
  const chartData = summary?.series.map((point) => ({ date: point.date, value: Number(point.value) })) ?? [];
  const yearTicks = computeYearTicks(chartData.map((point) => point.date));

  // Цвет линии означает УРОВЕНЬ, а не направление: зелёная — капитал
  // положителен, красная — обязательств больше, чем имущества. Направление
  // и так сказано стрелкой и знаком суммы в шапке, и красить линию ещё и
  // им значило бы, что один и тот же зелёный отвечает на два разных
  // вопроса — и не отвечает толком ни на один.
  //
  // Переход вверх, из минуса в плюс, отдельно не отмечается: он и так
  // читается как хорошая новость, потому что заканчивается зелёным.
  const values = chartData.map((point) => point.value);
  const dataMin = values.length ? Math.min(...values) : 0;
  const dataMax = values.length ? Math.max(...values) : 0;
  const crossesZero = dataMin < 0 && dataMax > 0;
  const allNegative = values.length > 0 && dataMax <= 0;
  // Доля высоты от верхнего края до нуля, в процентах. Градиент считается
  // в долях рамки самой линии, а не оси: у SVG objectBoundingBox верх — это
  // максимум данных, низ — минимум. Поэтому нулю здесь не нужны ни границы
  // оси, ни её округления «до красивого».
  const zeroOffset = crossesZero ? `${(dataMax / (dataMax - dataMin)) * 100}%` : "0%";
  const levelColor = allNegative ? "var(--danger)" : "var(--success)";

  // Крупное число — это капитал на конец периода, а не всегда сегодняшний.
  // Когда период выбран свой и кончается в прошлом, об этом надо сказать:
  // иначе цифра под заголовком «Капитал» читается как «столько у меня
  // сейчас», а это уже неправда.
  const lastDate = chartData.length ? chartData[chartData.length - 1].date : null;
  const todayIso = new Date().toLocaleDateString("sv");
  const asOfPast = lastDate !== null && lastDate < todayIso;

  return (
    <Card>
      <CardHeader className="items-start">
        <div>
          <CardTitle>{t("nav.netWorth")}</CardTitle>
          <p
            className={cn(
              "mt-1.5 text-2xl font-semibold tabular-nums sm:text-[28px]",
              isUnderwater ? "text-danger" : "text-text-primary"
            )}
          >
            {isLoading ? "…" : formatCurrency(summary?.current ?? 0)}
          </p>
          {/* Быстрые деньги и личное имущество — отдельными строками.
              Одно число на всё удобно ровно до первого решения, которое на
              него опирают: шесть миллионов, из которых 5,8 — квартира, не
              отвечают ни на «могу ли я это купить», ни на «хватит ли до
              зарплаты». */}
          {summary && (
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-text-muted">
              <span>
                {t("netWorth.liquid")}:{" "}
                <span className="tabular-nums text-text-secondary">{formatCurrency(summary.liquid)}</span>
              </span>
              {Number(summary.personal_use) > 0 && (
                <span>
                  {t("netWorth.personalUseShort")}:{" "}
                  <span className="tabular-nums text-text-secondary">
                    {formatCurrency(summary.personal_use)}
                  </span>
                </span>
              )}
            </p>
          )}
          {asOfPast && lastDate && (
            <p className="mt-0.5 text-xs text-text-muted">
              {t("netWorth.asOf", { date: formatAxisDate(lastDate) })}
            </p>
          )}
          {summary && (
            <p
              className="mt-1 flex items-center gap-1 text-sm font-medium"
              style={{ color: trendColor }}
            >
              {isPositive ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
              {formatSignedCurrency(summary.change_amount)}
              {summary.change_percent !== null && ` (${isPositive ? "+" : ""}${summary.change_percent.toFixed(1)}%)`}
              <span className="font-normal text-text-muted">{t("netWorth.periodSuffix")}</span>
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <RangeSelector value={range} onChange={onRangeChange} />
          {range === "custom" && (
            <YearRangeSelector
              years={years}
              fromYear={customRange.fromYear}
              toYear={customRange.toYear}
              onChange={onCustomRangeChange}
            />
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-56 w-full sm:h-64">
          {isLoading || chartData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-text-muted">
              {isLoading ? t("common.loading") : t("netWorth.noChartData")}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
                <defs>
                  {/* Две остановки на одном смещении — это резкая граница
                      вместо перехода: нулевая отметка не размывается. */}
                  <linearGradient id="netWorthStroke" x1="0" y1="0" x2="0" y2="1">
                    {crossesZero ? (
                      <>
                        <stop offset="0%" stopColor="var(--success)" />
                        <stop offset={zeroOffset} stopColor="var(--success)" />
                        <stop offset={zeroOffset} stopColor="var(--danger)" />
                        <stop offset="100%" stopColor="var(--danger)" />
                      </>
                    ) : (
                      <>
                        <stop offset="0%" stopColor={levelColor} />
                        <stop offset="100%" stopColor={levelColor} />
                      </>
                    )}
                  </linearGradient>
                  <linearGradient id="netWorthFill" x1="0" y1="0" x2="0" y2="1">
                    {crossesZero ? (
                      <>
                        <stop offset="0%" stopColor="var(--success)" stopOpacity={0.18} />
                        <stop offset={zeroOffset} stopColor="var(--success)" stopOpacity={0} />
                        <stop offset={zeroOffset} stopColor="var(--danger)" stopOpacity={0} />
                        <stop offset="100%" stopColor="var(--danger)" stopOpacity={0.18} />
                      </>
                    ) : (
                      <>
                        <stop offset="0%" stopColor={levelColor} stopOpacity={0.18} />
                        <stop offset="100%" stopColor={levelColor} stopOpacity={0} />
                      </>
                    )}
                  </linearGradient>
                </defs>
                <YAxis hide domain={["auto", "auto"]} />
                {yearTicks.length > 0 && (
                  <XAxis
                    dataKey="date"
                    type="category"
                    ticks={yearTicks}
                    tickFormatter={(value: string) => value.slice(0, 4)}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                    interval="preserveStartEnd"
                  />
                )}
                <Tooltip isAnimationActive={false} content={<ChartTooltip />} cursor={LINE_CURSOR} />
                {/* Нулевая отметка рисуется только когда линия её
                    пересекает. Иначе это лишняя черта, объясняющая то, чего
                    на графике не происходит. */}
                {crossesZero && <ReferenceLine y={0} stroke="var(--gridline)" strokeWidth={1} />}
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="url(#netWorthStroke)"
                  strokeWidth={2}
                  fill="url(#netWorthFill)"
                  // Заливка отсчитывается от нуля, а не от низа графика:
                  // иначе отрицательный участок закрашивался бы вверх от
                  // пола и читался бы как большой запас там, где на самом
                  // деле долг.
                  baseValue={crossesZero ? 0 : undefined}
                  isAnimationActive={false}
                  // Точка под курсором — акцентом, а не цветом линии: цвет
                  // линии здесь градиент, и на кружке диаметром в четыре
                  // точки он превратился бы в половину зелёного и половину
                  // красного независимо от того, где эта точка стоит.
                  activeDot={{ r: 4, strokeWidth: 0, fill: "var(--accent)" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
        {chartData.length > 1 && (
          <div className="mt-2 flex justify-between text-xs text-text-muted">
            <span>{formatAxisDate(chartData[0].date)}</span>
            <span>{formatAxisDate(chartData[chartData.length - 1].date)}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
