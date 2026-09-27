import { useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label, Select } from "@/components/ui/Input";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { useRateHistory } from "@/hooks/useCurrencies";
import { CURRENCIES } from "@/lib/currency";
import { formatRate, formatTransactionDate, getMonthLabels } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** Неделя, месяц или год — три вопроса, которые задают к курсу. */
type Period = "week" | "month" | "year";

/** Сколько лет предлагать в выборе. Источник отдаёт курсы с девяносто
 *  второго года, но выбор из тридцати лет — это список, в котором ищут, а не
 *  выбирают. */
const YEARS_OFFERED = 10;

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

/** Начало и конец выбранного периода. Конец обрезает сервер сегодняшним
 *  днём: курса на будущее не существует. */
function periodRange(period: Period, year: number, month: number): { start: string; end: string } {
  const today = new Date();
  if (period === "week") {
    const start = new Date(today);
    // Семь точек вместе с сегодняшней.
    start.setDate(start.getDate() - 6);
    return { start: isoDate(start), end: isoDate(today) };
  }
  if (period === "month") {
    return {
      start: isoDate(new Date(Date.UTC(year, month - 1, 1))),
      end: isoDate(new Date(Date.UTC(year, month, 0))),
    };
  }
  return {
    start: isoDate(new Date(Date.UTC(year, 0, 1))),
    end: isoDate(new Date(Date.UTC(year, 11, 31))),
  };
}

/**
 * График курса одной валюты за выбранный период.
 *
 * Открывается нажатием на строку в блоке «Курсы». До этого история была
 * недоступна вовсе: курс хранился только за те дни, когда его загружали, и
 * вопрос «а что было в марте» оставался без ответа.
 *
 * Периодов три, потому что и вопросов три: «что происходит сейчас» — неделя
 * по дням, «как прошёл месяц» — месяц по дням, «что было за год» — год по
 * месяцам. Отдельно — курс на конкретную дату: он нужен, когда сверяют
 * старую операцию.
 *
 * Недостающие дни догружаются на сервере при открытии (см.
 * cbr_service.sync_history): держать всю историю всех валют на всякий случай
 * незачем, а спросить её за раз — одно обращение на валюту.
 */
export function RateHistoryModal({ code, onClose }: { code: string | null; onClose: () => void }) {
  const { t, language } = useTranslation();
  const today = new Date();
  const [period, setPeriod] = useState<Period>("week");
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [onDate, setOnDate] = useState("");

  const range = periodRange(period, year, month);
  const history = useRateHistory(code, range.start, range.end, period === "year");
  // Курс на дату — отдельный короткий запрос тем же маршрутом: один день и
  // есть период из одного дня.
  const single = useRateHistory(onDate ? code : null, onDate, onDate, false);

  const points = history.data?.points ?? [];
  const first = points.at(0);
  const last = points.at(-1);
  const change = first && last ? Number(last.rate) - Number(first.rate) : null;
  const values = points.map((point) => Number(point.rate));
  const monthLabels = getMonthLabels(language);
  const currency = CURRENCIES.find((item) => item.code === code);
  const name = currency ? (language === "ru" ? currency.nameRu : currency.nameEn) : "";

  const periods: Array<{ key: Period; label: string }> = [
    { key: "week", label: t("rates.periodWeek") },
    { key: "month", label: t("rates.periodMonth") },
    { key: "year", label: t("rates.periodYear") },
  ];

  return (
    <Dialog
      wide
      open={code !== null}
      onClose={onClose}
      title={
        <span className="flex min-w-0 items-baseline gap-2">
          <span>{code}</span>
          <span className="truncate text-sm font-normal text-text-muted">{name}</span>
        </span>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-1">
            {periods.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setPeriod(item.key)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium",
                  period === item.key
                    ? "bg-surface-2 text-text-primary"
                    : "text-text-muted hover:bg-surface-2 hover:text-text-primary"
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
          {/* Месяц и год — только там, где они что-то меняют: у недели
              выбирать нечего, она всегда последняя. */}
          {period === "month" && (
            <Select
              value={month}
              onChange={(event) => setMonth(Number(event.target.value))}
              className="w-28"
            >
              {monthLabels.map((label, index) => (
                <option key={label} value={index + 1}>
                  {label}
                </option>
              ))}
            </Select>
          )}
          {period !== "week" && (
            <Select
              value={year}
              onChange={(event) => setYear(Number(event.target.value))}
              className="w-24"
            >
              {Array.from({ length: YEARS_OFFERED }, (_, index) => today.getFullYear() - index).map(
                (option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                )
              )}
            </Select>
          )}
        </div>

        {history.data?.source_unavailable && (
          <p className="text-xs text-text-muted">{t("rates.sourceUnavailable")}</p>
        )}

        {history.isLoading ? (
          <p className="py-16 text-center text-sm text-text-muted">{t("common.loading")}</p>
        ) : points.length === 0 ? (
          <p className="py-16 text-center text-sm text-text-muted">{t("rates.noData")}</p>
        ) : (
          <>
            <div className="h-52 w-full sm:h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                    tickFormatter={(value: string) =>
                      period === "year"
                        ? monthLabels[new Date(`${value}T00:00:00`).getMonth()]
                        : formatTransactionDate(value)
                    }
                    axisLine={false}
                    tickLine={false}
                    minTickGap={20}
                  />
                  {/* Своя область значений, а не от нуля: курс ходит на
                      проценты, и от нуля линия была бы прямой. */}
                  <YAxis
                    domain={[
                      (min: number) => min - (Math.max(...values) - Math.min(...values) || 1) * 0.2,
                      (max: number) => max + (Math.max(...values) - Math.min(...values) || 1) * 0.2,
                    ]}
                    tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                    tickFormatter={(value: number) => formatRate(value)}
                    axisLine={false}
                    tickLine={false}
                    width={56}
                  />
                  <Line
                    type="linear"
                    dataKey="rate"
                    stroke="var(--series-1)"
                    strokeWidth={2}
                    dot={points.length <= 14 ? { r: 2.5 } : false}
                    isAnimationActive={false}
                  />
                  <Tooltip isAnimationActive={false} content={<RateTooltip />} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="grid grid-cols-3 gap-3 border-t border-gridline pt-3 text-sm">
              <Figure label={t("rates.min")} value={formatRate(Math.min(...values))} />
              <Figure label={t("rates.max")} value={formatRate(Math.max(...values))} />
              <Figure
                label={t("rates.periodChange")}
                value={
                  change === null
                    ? "—"
                    : `${change > 0 ? "+" : change < 0 ? "−" : ""}${formatRate(Math.abs(change))}`
                }
                // Вверх зелёное, вниз красное — как и в самой карточке курсов.
                color={
                  change === null || change === 0
                    ? undefined
                    : change > 0
                      ? "var(--success)"
                      : "var(--danger)"
                }
              />
            </div>
          </>
        )}

        {/* Курс на конкретную дату: вопрос из разряда «а по какому курсу
            посчитана та операция». */}
        <div className="border-t border-gridline pt-3">
          <Label htmlFor="rate-on-date">{t("rates.rateOnDate")}</Label>
          <div className="flex flex-wrap items-center gap-3">
            <Input
              id="rate-on-date"
              type="date"
              value={onDate}
              max={isoDate(today)}
              onChange={(event) => setOnDate(event.target.value)}
              className="w-44"
            />
            <span className="text-sm font-medium tabular-nums">
              {!onDate
                ? ""
                : single.isLoading
                  ? "…"
                  : single.data?.points.length
                    ? formatRate(single.data.points[single.data.points.length - 1].rate)
                    : t("rates.noData")}
            </span>
          </div>
        </div>
      </div>
    </Dialog>
  );
}

function Figure({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <span className="block">
      <span className="block text-xs text-text-muted">{label}</span>
      <span className="block font-medium tabular-nums" style={color ? { color } : undefined}>
        {value}
      </span>
    </span>
  );
}

function RateTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: { date: string; rate: string } }>;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <ChartTooltipBox>
      <p className="text-text-muted">{formatTransactionDate(point.date, true)}</p>
      <p className="font-medium tabular-nums text-text-primary">{formatRate(point.rate)}</p>
    </ChartTooltipBox>
  );
}
