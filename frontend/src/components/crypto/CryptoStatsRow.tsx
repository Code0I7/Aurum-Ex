import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/Card";
import { formatCurrency, maskAmount } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding } from "@/types";

interface CryptoStatsRowProps {
  holdings: CryptoHolding[];
  isLoading: boolean;
  hidden: boolean;
}

interface Totals {
  totalValue: number;
  totalCostBasis: number;
  totalProfitLoss: number;
  totalProfitLossPercent: number | null;
  best: CryptoHolding | null;
  worst: CryptoHolding | null;
}

function computeTotals(holdings: CryptoHolding[]): Totals {
  let totalValue = 0;
  let totalCostBasis = 0;
  let best: CryptoHolding | null = null;
  let worst: CryptoHolding | null = null;

  for (const holding of holdings) {
    if (holding.value !== null) totalValue += Number(holding.value);
    if (holding.cost_basis !== null) totalCostBasis += Number(holding.cost_basis);
    if (holding.profit_loss_percent === null) continue;
    if (best === null || holding.profit_loss_percent > best.profit_loss_percent!) best = holding;
    if (worst === null || holding.profit_loss_percent < worst.profit_loss_percent!) worst = holding;
  }

  const totalProfitLoss = totalValue - totalCostBasis;
  const totalProfitLossPercent = totalCostBasis > 0 ? (totalProfitLoss / totalCostBasis) * 100 : null;

  return { totalValue, totalCostBasis, totalProfitLoss, totalProfitLossPercent, best, worst };
}

function StatTile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Card>
      <CardContent className="p-3.5 sm:p-4">
        <p className="text-xs uppercase tracking-wide text-text-muted">{label}</p>
        <div className="mt-1.5">{children}</div>
      </CardContent>
    </Card>
  );
}

function PerformerTile({ label, holding }: { label: string; holding: CryptoHolding | null }) {
  const { t } = useTranslation();
  if (holding === null || holding.profit_loss_percent === null) {
    return (
      <StatTile label={label}>
        <p className="text-lg font-semibold text-text-muted">—</p>
      </StatTile>
    );
  }
  const percent = holding.profit_loss_percent;
  const color = percent >= 0 ? "var(--success)" : "var(--danger)";
  return (
    <StatTile label={label}>
      <div className="flex items-center gap-2">
        {holding.thumb_url ? (
          <img src={holding.thumb_url} alt="" className="h-5 w-5 shrink-0 rounded-full" />
        ) : (
          <span className="h-5 w-5 shrink-0 rounded-full bg-surface-2" />
        )}
        <p className="truncate text-lg font-semibold text-text-primary">{holding.symbol}</p>
      </div>
      <p className="mt-0.5 text-sm font-medium tabular-nums" style={{ color }}>
        {percent >= 0 ? "+" : ""}
        {percent.toFixed(2)}%
      </p>
      <p className="mt-0.5 text-xs text-text-muted">{t("crypto.stats.since", { name: holding.name })}</p>
    </StatTile>
  );
}

export function CryptoStatsRow({ holdings, isLoading, hidden }: CryptoStatsRowProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return <p className="py-4 text-center text-sm text-text-muted">{t("common.loading")}</p>;
  }
  if (holdings.length === 0) return null;

  const totals = computeTotals(holdings);
  const profitColor = totals.totalProfitLoss >= 0 ? "var(--success)" : "var(--danger)";

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatTile label={t("crypto.stats.allTimeProfit")}>
        <p className="text-lg font-semibold tabular-nums" style={{ color: profitColor }}>
          {maskAmount(`${totals.totalProfitLoss >= 0 ? "+" : ""}${formatCurrency(totals.totalProfitLoss)}`, hidden)}
        </p>
        {totals.totalProfitLossPercent !== null && (
          <p className="mt-0.5 text-sm font-medium tabular-nums" style={{ color: profitColor }}>
            {totals.totalProfitLossPercent >= 0 ? "+" : ""}
            {totals.totalProfitLossPercent.toFixed(2)}%
          </p>
        )}
      </StatTile>

      <StatTile label={t("crypto.stats.costBasis")}>
        <p className="text-lg font-semibold tabular-nums text-text-primary">
          {maskAmount(formatCurrency(totals.totalCostBasis), hidden)}
        </p>
        <p className="mt-0.5 text-xs text-text-muted">{t("crypto.stats.costBasisHint")}</p>
      </StatTile>

      <PerformerTile label={t("crypto.stats.bestPerformer")} holding={totals.best} />
      <PerformerTile label={t("crypto.stats.worstPerformer")} holding={totals.worst} />
    </div>
  );
}
