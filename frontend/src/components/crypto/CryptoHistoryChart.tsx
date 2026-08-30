import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { ArrowDown, ArrowUp, Eye, EyeOff } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { CryptoRangeSelector } from "@/components/crypto/CryptoRangeSelector";
import { formatCurrency, formatSignedCurrency, getIntlLocale, maskAmount } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHistoryResponse, CryptoRange } from "@/types";

interface CryptoHistoryChartProps {
  history: CryptoHistoryResponse | undefined;
  isLoading: boolean;
  range: CryptoRange;
  onRangeChange: (range: CryptoRange) => void;
  hidden: boolean;
  onToggleHidden: () => void;
}

function formatAxisDate(iso: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { month: "short", day: "numeric" }).format(new Date(`${iso}T00:00:00`));
}

function ChartTooltip({
  active,
  payload,
  hidden,
}: {
  active?: boolean;
  payload?: Array<{ payload: { date: string; value: number } }>;
  hidden: boolean;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm shadow-md">
      <p className="text-text-muted">{formatAxisDate(point.date)}</p>
      <p className="font-medium text-text-primary">{maskAmount(formatCurrency(point.value), hidden)}</p>
    </div>
  );
}

/** The Crypto tab's headline chart — same recipe as NetWorthChart, plus an
 * eye toggle. `hidden` is owned by CryptoPage and passed to every other
 * money-displaying section of the tab too — this is just where the toggle
 * button itself lives. */
export function CryptoHistoryChart({
  history,
  isLoading,
  range,
  onRangeChange,
  hidden,
  onToggleHidden,
}: CryptoHistoryChartProps) {
  const { t } = useTranslation();
  const isPositive = history ? Number(history.change_amount) >= 0 : true;
  const trendColor = isPositive ? "var(--success)" : "var(--danger)";
  const chartData = history?.series.map((point) => ({ date: point.date, value: Number(point.value) })) ?? [];

  return (
    <Card>
      <CardHeader className="flex-col items-stretch gap-3 sm:flex-row sm:items-start">
        <div>
          <CardTitle>{t("nav.crypto")}</CardTitle>
          <p className="mt-1.5 flex items-center gap-2 text-2xl font-semibold tabular-nums text-text-primary sm:text-[28px]">
            {isLoading ? "…" : maskAmount(formatCurrency(history?.current ?? 0), hidden)}
            <button
              type="button"
              aria-label={hidden ? t("crypto.chart.show") : t("crypto.chart.hide")}
              onClick={onToggleHidden}
              className="text-text-muted hover:text-text-primary"
            >
              {hidden ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </p>
          {history && (
            <p className="mt-1 flex items-center gap-1 text-sm font-medium" style={{ color: trendColor }}>
              {isPositive ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
              {maskAmount(formatSignedCurrency(history.change_amount), hidden)}
              {history.change_percent !== null && ` (${isPositive ? "+" : ""}${history.change_percent.toFixed(1)}%)`}
              <span className="font-normal text-text-muted">{t("netWorth.periodSuffix")}</span>
            </p>
          )}
        </div>
        <CryptoRangeSelector value={range} onChange={onRangeChange} />
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
                  <linearGradient id="cryptoHistoryFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={trendColor} stopOpacity={0.18} />
                    <stop offset="100%" stopColor={trendColor} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <YAxis hide domain={["auto", "auto"]} />
                <Tooltip content={<ChartTooltip hidden={hidden} />} cursor={{ stroke: "var(--gridline)", strokeWidth: 1 }} />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={trendColor}
                  strokeWidth={2}
                  fill="url(#cryptoHistoryFill)"
                  isAnimationActive={false}
                  activeDot={{ r: 4, strokeWidth: 0 }}
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
