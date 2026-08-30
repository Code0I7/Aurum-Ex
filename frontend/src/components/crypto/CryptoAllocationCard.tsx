import { Bitcoin } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { formatCurrency, maskAmount } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding } from "@/types";

interface CryptoAllocationCardProps {
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

export function CryptoAllocationCard({ holdings, isLoading, hidden }: CryptoAllocationCardProps) {
  const { t } = useTranslation();
  const slices = buildSlices(holdings);
  const total = slices.reduce((sum, slice) => sum + slice.amount, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("crypto.allocation.title")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
        ) : slices.length === 0 ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("crypto.empty")}</p>
        ) : (
          <>
            <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-surface-2">
              {slices.map((slice) => (
                <div
                  key={slice.key}
                  style={{ width: `${(slice.amount / total) * 100}%`, backgroundColor: slice.color }}
                  className="h-full first:rounded-l-full last:rounded-r-full"
                />
              ))}
            </div>

            <ul className="mt-4 divide-y divide-gridline border-t border-gridline">
              {slices.map((slice) => {
                const percent = (slice.amount / total) * 100;
                return (
                  <li key={slice.key} className="flex items-center gap-3 py-2.5 first:pt-3">
                    {slice.thumbUrl ? (
                      <img src={slice.thumbUrl} alt="" className="h-7 w-7 shrink-0 rounded-full" />
                    ) : (
                      <span
                        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                        style={{ backgroundColor: `${slice.color}26` }}
                      >
                        <Bitcoin size={14} style={{ color: slice.color }} />
                      </span>
                    )}
                    <span className="min-w-0 flex-1 truncate text-sm text-text-primary">
                      {slice.key === "other" ? t("crypto.allocation.other") : slice.name}
                      {slice.symbol && <span className="text-text-muted"> · {slice.symbol}</span>}
                    </span>
                    <span className="hidden w-24 shrink-0 items-center gap-2 sm:flex">
                      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                        <span className="block h-full rounded-full" style={{ width: `${percent}%`, backgroundColor: slice.color }} />
                      </span>
                      <span className="w-9 shrink-0 text-right text-xs text-text-muted tabular-nums">{percent.toFixed(0)}%</span>
                    </span>
                    <span className="w-14 shrink-0 text-right text-xs text-text-muted tabular-nums sm:hidden">
                      {percent.toFixed(0)}%
                    </span>
                    <span className="shrink-0 text-sm font-medium tabular-nums text-text-primary">
                      {maskAmount(formatCurrency(slice.amount), hidden)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
