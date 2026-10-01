import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDown, ArrowUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { RangeSelector } from "@/components/layout/RangeSelector";
import { DateRangeSelector } from "@/components/layout/YearSelector";
import type { CustomDateRange } from "@/lib/dateRange";
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
  customRange: CustomDateRange;
  onCustomRangeChange: (range: CustomDateRange) => void;
  // Валюта, в которой смотрят капитал. Пусто — своя: подставит сервер.
  currency: string;
  onCurrencyChange: (currency: string) => void;
}

function formatAxisDate(iso: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { month: "short", day: "numeric", year: "numeric" }).format(
    new Date(`${iso}T00:00:00`)
  );
}

/** Точка кривой. `above` и `below` — тот же ряд, разрезанный по нулю:
 *  выше нуля рисует зелёная линия, ниже — красная, и каждая половина
 *  ничего не знает о другой. Пустое место второй половины — null, а не
 *  ноль: ноль нарисовал бы линию по оси там, где её нет. */
interface ChartPoint {
  date: string;
  value: number;
  above: number | null;
  below: number | null;
}

/** Ряд, разрезанный по нулю, с добавленным днём перехода.
 *
 *  Между «вчера плюс» и «сегодня минус» в данных нет дня, когда капитал
 *  равен нулю: там просто соседние точки разных знаков. Без вставленной
 *  точки обе половины оборвались бы, не дойдя до оси, и на коротком
 *  периоде в линии зияла бы дыра шириной в сутки.
 *
 *  Вставка получает дату следующего дня: переход случился в промежутке
 *  между двумя записями, и день, которым он закончился, — ближайшее
 *  честное к нему число.
 *
 *  Ноль лежит только в `above`/`below`, а `value` у вставки — настоящее
 *  значение того дня. Ноль нужен геометрии, а подсказка читает `value`, и
 *  показывать в ней выдуманный ноль нельзя: 7 сентября 2024 капитал был
 *  +4 680,81, и «0,00 ₽» в этом месте — число, которого не было. */
function splitAtZero(points: Array<{ date: string; value: number }>): ChartPoint[] {
  const split: ChartPoint[] = [];
  points.forEach((point, index) => {
    const previous = index > 0 ? points[index - 1] : null;
    if (previous !== null && previous.value * point.value < 0) {
      split.push({ date: point.date, value: point.value, above: 0, below: 0 });
    }
    split.push({
      date: point.date,
      value: point.value,
      above: point.value >= 0 ? point.value : null,
      below: point.value <= 0 ? point.value : null,
    });
  });
  return split;
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

function ChartTooltip({
  active,
  payload,
  // Валюта кривой. Без неё подсказка подписывала бы долларовый капитал
  // значком валюты установки — то самое молчаливое враньё, ради ухода от
  // которого кривая и считается в одной валюте.
  currency,
}: {
  active?: boolean;
  payload?: Array<{ payload: { date: string; value: number } }>;
  currency?: string;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <ChartTooltipBox>
      <p className="text-text-muted">{formatAxisDate(point.date)}</p>
      <p className="font-medium text-text-primary">{formatCurrency(point.value, currency)}</p>
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
  currency,
  onCurrencyChange,
}: NetWorthChartProps) {
  const { t, currency: base } = useTranslation();
  // Валюта самой кривой. Пока ответа нет — та, что выбрана, а на первом
  // открытии валюта установки: подписать ось «₽» и потом молча сменить
  // подпись хуже, чем подождать.
  const shown = summary?.currency || currency || base;
  const isPositive = summary ? Number(summary.change_amount) >= 0 : true;
  const trendColor = isPositive ? "var(--success)" : "var(--danger)";
  // Отрицательный капитал — это долгов больше, чем имущества, и число
  // должно об этом сказать само. Знак минуса в общем ряду цифр теряется,
  // а цвет виден раньше, чем прочитана сумма.
  const isUnderwater = summary ? Number(summary.current) < 0 : false;
  const series = summary?.series.map((point) => ({ date: point.date, value: Number(point.value) })) ?? [];

  // Цвет линии означает УРОВЕНЬ, а не направление: зелёная — капитал
  // положителен, красная — обязательств больше, чем имущества. Направление
  // и так сказано стрелкой и знаком суммы в шапке, и красить линию ещё и
  // им значило бы, что один и тот же зелёный отвечает на два разных
  // вопроса — и не отвечает толком ни на один.
  //
  // Переход вверх, из минуса в плюс, отдельно не отмечается: он и так
  // читается как хорошая новость, потому что заканчивается зелёным.
  //
  // Цвет — свойство ДАННЫХ, а не картинки: ряд разрезан по нулю, и зелёной
  // линии ниже оси просто не из чего рисоваться. Одна линия с градиентом
  // это условие держать не умеет: граница цвета в ней задаётся долей рамки
  // линии, а рамка зависит от того, что попало в период. Стоит заливке
  // разойтись с данными — а при смене периода она разошлась, — и зелёное
  // уезжает под ноль на десятки пикселей.
  const values = series.map((point) => point.value);
  const dataMin = values.length ? Math.min(...values) : 0;
  const dataMax = values.length ? Math.max(...values) : 0;
  const crossesZero = dataMin < 0 && dataMax > 0;
  const allNegative = values.length > 0 && dataMax <= 0;
  const levelColor = allNegative ? "var(--danger)" : "var(--success)";
  const chartData = splitAtZero(series);
  const yearTicks = computeYearTicks(chartData.map((point) => point.date));
  // Точка под курсором — цветом своей линии: у каждой половины он свой и
  // постоянный, так что кружок больше нечем путать.
  const activeDot = { r: 4, strokeWidth: 0 };

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
            {isLoading ? "…" : formatCurrency(summary?.current ?? 0, shown)}
          </p>
          {/* Три величины в одну строку.

              Капитал — состояние, и переводить его нельзя: сто евро на
              евровой карте это сто евро, а не их сегодняшняя цена в
              рублях. Поэтому крупное число — это выбранная валюта и
              ничего кроме неё.

              Остальное сведено в одну величину и переведено по
              сегодняшнему курсу — иначе его не выразить, евро с юанями не
              складываются. Отсюда «≈»: это оценка на сегодня, а не то,
              что лежит на счетах. Ни второй строки, ни третьей не
              появляется, пока всё в одной валюте. */}
          {summary && Number(summary.other_base) !== 0 && (
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-text-muted">
              <span>
                {t("netWorth.inOtherCurrencies")}:{" "}
                <span className="tabular-nums text-text-secondary">
                  ≈ {formatCurrency(summary.other_base, base)}
                </span>
              </span>
              <span>
                {t("netWorth.totalEverything")}:{" "}
                <span className="tabular-nums text-text-secondary">
                  ≈ {formatCurrency(summary.total_base, base)}
                </span>
              </span>
            </p>
          )}
          {/* Быстрые деньги и личное имущество — отдельными строками.
              Одно число на всё удобно ровно до первого решения, которое на
              него опирают: шесть миллионов, из которых 5,8 — квартира, не
              отвечают ни на «могу ли я это купить», ни на «хватит ли до
              зарплаты». */}
          {summary && (
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-text-muted">
              <span>
                {t("netWorth.liquid")}:{" "}
                <span className="tabular-nums text-text-secondary">
                  {formatCurrency(summary.liquid, shown)}
                </span>
              </span>
              {Number(summary.personal_use) > 0 && (
                <span>
                  {t("netWorth.personalUseShort")}:{" "}
                  <span className="tabular-nums text-text-secondary">
                    {formatCurrency(summary.personal_use, shown)}
                  </span>
                </span>
              )}
              {/* Долг по кредиткам и рассрочкам. Он уже вычтен из капитала;
                  строка объясняет итог — «72 тысячи, когда на счетах 127» —
                  и появляется, только когда должно что-то. */}
              {Number(summary.liabilities) > 0 && (
                <span>
                  {t("netWorth.liabilitiesShort")}:{" "}
                  <span className="tabular-nums text-danger">
                    −{formatCurrency(summary.liabilities, shown)}
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
              {formatSignedCurrency(summary.change_amount, shown)}
              {summary.change_percent !== null && ` (${isPositive ? "+" : ""}${summary.change_percent.toFixed(1)}%)`}
              <span className="font-normal text-text-muted">{t("netWorth.periodSuffix")}</span>
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {/* Переключатель валют появляется, только когда переключать есть
              на что: у установки с одной валютой он был бы кнопкой, которая
              ничего не делает. */}
          {summary && summary.currencies.length > 1 && (
            <span className="flex items-center gap-1">
              {summary.currencies.map((code) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => onCurrencyChange(code)}
                  className={cn(
                    "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                    code === shown
                      ? "bg-surface-2 text-text-primary"
                      : "text-text-muted hover:bg-surface-2 hover:text-text-primary"
                  )}
                >
                  {code}
                </button>
              ))}
            </span>
          )}
          <RangeSelector value={range} onChange={onRangeChange} />
          {range === "custom" && (
            <DateRangeSelector
              years={years}
              value={customRange}
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
                {/* Заливки постоянные: ни одна не зависит ни от данных, ни
                    от периода. Раньше здесь считалось, где у линии ноль, и
                    именно это число при смене периода оставалось старым.
                    Теперь каждая заливка накрывает ровно одну сторону оси, и
                    ошибиться ей негде — в худшем случае разойдётся густота. */}
                <defs>
                  {/* Над нулём: густо у линии, прозрачно у оси. */}
                  <linearGradient id="netWorthFillAbove" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--success)" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="var(--success)" stopOpacity={0} />
                  </linearGradient>
                  {/* Под нулём: прозрачно у оси, густо у самой глубокой точки. */}
                  <linearGradient id="netWorthFillBelow" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--danger)" stopOpacity={0} />
                    <stop offset="100%" stopColor="var(--danger)" stopOpacity={0.18} />
                  </linearGradient>
                  {/* Весь период в минусе: оси на графике нет, и заливка
                      отсчитывается от линии вниз, как у положительной. */}
                  <linearGradient id="netWorthFillOnlyBelow" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--danger)" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="var(--danger)" stopOpacity={0} />
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
                <Tooltip
                  isAnimationActive={false}
                  content={<ChartTooltip currency={shown} />}
                  cursor={LINE_CURSOR}
                />
                {/* Нулевая отметка рисуется только когда линия её
                    пересекает. Иначе это лишняя черта, объясняющая то, чего
                    на графике не происходит. */}
                {crossesZero && <ReferenceLine y={0} stroke="var(--gridline)" strokeWidth={1} />}
                {crossesZero ? (
                  <>
                    {/* Заливка отсчитывается от нуля, а не от низа графика:
                        иначе отрицательный участок закрашивался бы вверх от
                        пола и читался бы как большой запас там, где на самом
                        деле долг. connectNulls={false} обязателен: без него
                        линия перепрыгнет через чужой участок по прямой. */}
                    <Area
                      type="monotone"
                      dataKey="above"
                      stroke="var(--success)"
                      strokeWidth={2}
                      fill="url(#netWorthFillAbove)"
                      baseValue={0}
                      connectNulls={false}
                      isAnimationActive={false}
                      activeDot={{ ...activeDot, fill: "var(--success)" }}
                    />
                    <Area
                      type="monotone"
                      dataKey="below"
                      stroke="var(--danger)"
                      strokeWidth={2}
                      fill="url(#netWorthFillBelow)"
                      baseValue={0}
                      connectNulls={false}
                      isAnimationActive={false}
                      activeDot={{ ...activeDot, fill: "var(--danger)" }}
                    />
                  </>
                ) : (
                  /* Период целиком по одну сторону нуля: резать нечего, и
                     заливке незачем упираться в ось, которой не видно. */
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke={levelColor}
                    strokeWidth={2}
                    fill={allNegative ? "url(#netWorthFillOnlyBelow)" : "url(#netWorthFillAbove)"}
                    isAnimationActive={false}
                    activeDot={{ ...activeDot, fill: levelColor }}
                  />
                )}
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
