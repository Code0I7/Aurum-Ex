import { Bitcoin } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { formatCurrency, maskAmount } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding } from "@/types";

interface CryptoAllocationBodyProps {
  holdings: CryptoHolding[];
  isLoading: boolean;
  hidden: boolean;
}

// Fixed categorical order, same 8-slot ramp the rest of the app already
// validated (see net_worth_service.py's _CLASS_META comment) — a coin never
// gets a freshly generated hue. Only the first 7 get their own color; an 8th+
// coin folds into "Other" (--series-other) rather than cycling back through
// the ramp, per the dataviz skill's categorical-color rule.
const SERIES_COLORS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
];
const OTHER_COLOR = "var(--series-other)";
const MAX_SLICES = SERIES_COLORS.length;

interface Slice {
  key: string;
  name: string;
  symbol: string | null;
  thumbUrl: string | null;
  amount: number;
  color: string;
}

function buildSlices(holdings: CryptoHolding[]): Slice[] {
  const priced = holdings
    .filter((h) => h.value !== null && Number(h.value) > 0)
    .map((h) => ({ key: String(h.asset_id), name: h.name, symbol: h.symbol, thumbUrl: h.thumb_url, amount: Number(h.value) }))
    .sort((a, b) => b.amount - a.amount);

  const top = priced.slice(0, MAX_SLICES).map((item, index) => ({ ...item, color: SERIES_COLORS[index] }));
  const rest = priced.slice(MAX_SLICES);
  if (rest.length === 0) return top;

  const otherTotal = rest.reduce((sum, item) => sum + item.amount, 0);
  return [...top, { key: "other", name: "Other", symbol: null, thumbUrl: null, amount: otherTotal, color: OTHER_COLOR }];
}

function DonutTooltip({
  active,
  payload,
  hidden,
  otherLabel,
}: {
  active?: boolean;
  payload?: Array<{ payload: Slice & { percent: number } }>;
  hidden: boolean;
  otherLabel: string;
}) {
  if (!active || !payload?.length) return null;
  const slice = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm shadow-md">
      <p className="font-medium text-text-primary">{slice.key === "other" ? otherLabel : slice.name}</p>
      <p className="text-text-muted">
        {maskAmount(formatCurrency(slice.amount), hidden)} · {slice.percent.toFixed(1)}%
      </p>
    </div>
  );
}

/** The "Allocation" tab's content inside CryptoOverviewCard — a donut (part-
 * to-whole across few categories is exactly the case a donut is fine for)
 * plus a list that also carries the $ amount, which the donut/legend alone
 * can't — the user explicitly wants both percent and sum per coin, not just
 * percent the way CoinMarketCap's own version shows it. */
export function CryptoAllocationBody({ holdings, isLoading, hidden }: CryptoAllocationBodyProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>;
  }
  const slices = buildSlices(holdings);
  if (slices.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("crypto.empty")}</p>;
  }

  const total = slices.reduce((sum, slice) => sum + slice.amount, 0);
  const donutData = slices.map((slice) => ({ ...slice, percent: (slice.amount / total) * 100 }));

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center sm:justify-center sm:gap-8">
      <div className="h-48 w-48 shrink-0 sm:h-56 sm:w-56">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={donutData}
              dataKey="amount"
              nameKey="name"
              innerRadius="68%"
              outerRadius="100%"
              paddingAngle={donutData.length > 1 ? 2 : 0}
              stroke="var(--surface-1)"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {donutData.map((slice) => (
                <Cell key={slice.key} fill={slice.color} />
              ))}
            </Pie>
            <Tooltip content={<DonutTooltip hidden={hidden} otherLabel={t("crypto.allocation.other")} />} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Capped width, not flex-1 — otherwise with few/short coin names the
          row stretches across whatever's left of the card and the percent/
          amount columns end up stranded far from the coin they describe. */}
      <ul className="w-full min-w-0 divide-y divide-gridline sm:w-72">
        {donutData.map((slice) => (
          <li key={slice.key} className="flex items-center gap-3 py-2 first:pt-0">
            {slice.thumbUrl ? (
              <img src={slice.thumbUrl} alt="" className="h-6 w-6 shrink-0 rounded-full" />
            ) : (
              <span
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full"
                style={{ backgroundColor: `${slice.color}26` }}
              >
                <Bitcoin size={12} style={{ color: slice.color }} />
              </span>
            )}
            <span className="min-w-0 flex-1 truncate text-sm text-text-primary">
              {slice.key === "other" ? t("crypto.allocation.other") : slice.name}
              {slice.symbol && <span className="text-text-muted"> · {slice.symbol}</span>}
            </span>
            <span className="shrink-0 text-right text-sm font-medium tabular-nums text-text-primary">
              {slice.percent.toFixed(1)}%
            </span>
            <span className="w-20 shrink-0 text-right text-xs tabular-nums text-text-muted">
              {maskAmount(formatCurrency(slice.amount), hidden)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
