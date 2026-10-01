import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useTranslation, getLanguage } from "@/lib/i18n";
import { formatCurrency, formatSignedCurrency, getIntlLocale, getMonthLabels } from "@/lib/format";
import type { DashboardDayPoint, DashboardMonthPoint } from "@/types";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { BAR_CURSOR } from "@/components/charts/cursors";

/** Чем нарезан график: месяцами периода или днями выбранного месяца. */
type FlowStep = "months" | "days";

/** Короткая запись числа для подписей оси: «110 тыс.» вместо «110 000,00 ₽».
 *  Полная запись в шестизначные суммы не помещалась и обрезалась слева,
 *  превращая 110 000 в 10 000 — число, которого на графике нет. Точные
 *  суммы человек читает в подсказке, а ось нужна для порядка величин. */
function compact(value: number): string {
  return new Intl.NumberFormat(getIntlLocale(), {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(Math.abs(value));
}

function formatDayLabel(iso: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { day: "numeric", month: "long" }).format(
    new Date(`${iso}T00:00:00`)
  );
}

/**
 * Движение денег: по месяцам периода или по дням выбранного месяца.
 *
 * Считается тем же расчётом, что и страница «Движение ДС»: два разных
 * ответа на один вопрос — худшее, что приложение может показать про деньги.
 *
 * Месяцы отвечают на «как шёл год». Дни — на другой вопрос: куда делся
 * месяц. Там два-три прихода и три десятка расходов, и интересны не
 * столбцы сами по себе, а форма: когда пришла зарплата, как быстро она
 * растаяла, оставались ли дни без трат вовсе. Поэтому поверх дневных
 * столбцов идёт накопительная линия — она и есть ответ, а столбцы
 * показывают, из чего он сложился.
 *
 * За один месяц ряд месяцев не рисуется: столбик из одного значения не
 * показывает динамику, ради которой график и нужен. Зато ровно в этом
 * случае есть дни, и карточка показывает их.
 */
export function MonthlyFlowCard({
  points,
  daily,
}: {
  points: DashboardMonthPoint[];
  /** Дни выбранного месяца. Пусто, когда выбран не месяц: за год дневных
   *  столбцов 365, и прочитать в них нечего. */
  daily: DashboardDayPoint[];
}) {
  const { t } = useTranslation();
  const months = getMonthLabels(getLanguage());

  const hasMonths = points.length >= 2;
  const hasDays = daily.length > 0;
  if (!hasMonths && !hasDays) return null;
  // Переключателя у карточки нет, и он здесь не нужен: нарезку выбирает
  // период над обзором. Выбран месяц — дни существуют, а ряда месяцев
  // внутри него нет; выбран год или всё время — наоборот. Кнопка «показать
  // по дням» при выбранном годе вела бы на триста шестьдесят пять столбцов
  // шириной в полпикселя, и это не вид, а отказ отвечать.
  const shown: FlowStep = hasDays ? "days" : "months";

  const monthData = points.map((point) => ({
    label: `${months[point.month - 1].slice(0, 3)} ${String(point.year).slice(2)}`,
    income: Number(point.income),
    // Расход рисуется вниз: столбцы навстречу друг другу читаются как
    // «пришло / ушло» без легенды.
    expense: -Number(point.expense),
    net: Number(point.net),
  }));

  // Накопительный итог считается здесь, а не на сервере: это та же сумма
  // net по уже показанным дням, и считать её дважды незачем.
  let running = 0;
  const dayData = daily.map((point) => {
    running += Number(point.net);
    return {
      date: point.date,
      label: String(Number(point.date.slice(8, 10))),
      income: Number(point.income),
      expense: -Number(point.expense),
      net: Number(point.net),
      running,
    };
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {shown === "days" ? t("dashboard.dailyTitle") : t("dashboard.monthlyTitle")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-52 w-full sm:h-60">
          <div className="chart-palette h-full w-full">
            <ResponsiveContainer width="100%" height="100%">
              {shown === "months" ? (
                <BarChart
                  data={monthData}
                  margin={{ top: 5, right: 5, bottom: 5, left: 5 }}
                  stackOffset="sign"
                >
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
                    width={52}
                    tickFormatter={compact}
                  />
                  <Tooltip
                    isAnimationActive={false}
                    cursor={BAR_CURSOR}
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const point = payload[0].payload as (typeof monthData)[number];
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
                  {/* Тот же радиус, что у дохода, и это не опечатка. Скругляться
                      должен свободный конец столбца: у дохода верхний, у расхода
                      нижний. Но recharts задаёт радиус так, будто столбец растёт
                      вверх, и у отрицательного значения отражает фигуру вместе с
                      углами: объявленное «снизу» выходит наверху, у самой оси.
                      Проверено на стенде — у столбца от оси (y 135) до конца
                      (y 200) радиус [0,0,2,2] даёт дуги на 135…147, а [2,2,0,0]
                      на 188…200. */}
                  <Bar dataKey="expense" fill="var(--danger)" radius={[2, 2, 0, 0]} />
                </BarChart>
              ) : (
                <ComposedChart
                  data={dayData}
                  margin={{ top: 5, right: 5, bottom: 5, left: 5 }}
                  stackOffset="sign"
                >
                  <CartesianGrid stroke="var(--gridline)" vertical={false} />
                  {/* Подписи прореживаются сами: тридцать чисел подряд
                      сливаются в полосу, а minTickGap оставляет столько,
                      сколько помещается, не касаясь друг друга. */}
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                    stroke="var(--gridline)"
                    interval="preserveStartEnd"
                    minTickGap={14}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                    stroke="var(--gridline)"
                    width={52}
                    tickFormatter={compact}
                  />
                  <Tooltip
                    isAnimationActive={false}
                    cursor={BAR_CURSOR}
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const point = payload[0].payload as (typeof dayData)[number];
                      return (
                        <ChartTooltipBox className="text-xs">
                          <p className="text-text-muted">{formatDayLabel(point.date)}</p>
                          {/* Нулевые строки не печатаются: в большинстве дней
                              приход или расход пустой, и «0,00 ₽» в подсказке
                              занимает место, ничего не добавляя. */}
                          {point.income !== 0 && (
                            <p className="text-success">
                              {t("cashFlow.income")}: {formatCurrency(point.income)}
                            </p>
                          )}
                          {point.expense !== 0 && (
                            <p className="text-danger">
                              {t("cashFlow.expense")}: {formatCurrency(Math.abs(point.expense))}
                            </p>
                          )}
                          <p className="font-medium text-text-primary">
                            {t("dashboard.runningTotal")}: {formatSignedCurrency(point.running)}
                          </p>
                        </ChartTooltipBox>
                      );
                    }}
                  />
                  <Bar dataKey="income" fill="var(--success)" radius={[2, 2, 0, 0]} />
                  {/* Про радиус см. выше: столбец, растущий вниз, отражается
                      вместе со своими углами. */}
                  <Bar dataKey="expense" fill="var(--danger)" radius={[2, 2, 0, 0]} />
                  {/* Накопительная линия — главное на дневном графике: по ней
                      видно, в какой день месяц ушёл в минус. Точек на ней нет:
                      их было бы тридцать подряд, и линия превратилась бы в
                      пунктир из кружков. */}
                  <Line
                    type="monotone"
                    dataKey="running"
                    stroke="var(--accent)"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              )}
            </ResponsiveContainer>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
