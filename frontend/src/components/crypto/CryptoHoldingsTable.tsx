import { Bitcoin, Plus, Trash2 } from "lucide-react";
import { formatCurrency, maskAmount } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding } from "@/types";

interface CryptoHoldingsTableProps {
  items: CryptoHolding[];
  hidden: boolean;
  onTrade: (holding: CryptoHolding) => void;
  onViewHistory: (holding: CryptoHolding) => void;
  onDelete: (holding: CryptoHolding) => void;
}

function PercentCell({ value }: { value: string | null }) {
  if (value === null) return <span className="text-text-muted">—</span>;
  const num = Number(value);
  const color = num > 0 ? "var(--success)" : num < 0 ? "var(--danger)" : "var(--text-muted)";
  return (
    <span className="tabular-nums" style={{ color }}>
      {num > 0 ? "+" : ""}
      {num.toFixed(2)}%
    </span>
  );
}

export function CryptoHoldingsTable({ items, hidden, onTrade, onViewHistory, onDelete }: CryptoHoldingsTableProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("crypto.empty")}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-text-muted">
            <th className="py-2 pr-3 font-medium">{t("crypto.table.name")}</th>
            <th className="py-2 pr-3 text-right font-medium">{t("crypto.table.price")}</th>
            <th className="py-2 pr-3 text-right font-medium">{t("crypto.table.change1h")}</th>
            <th className="py-2 pr-3 text-right font-medium">{t("crypto.table.change24h")}</th>
            <th className="py-2 pr-3 text-right font-medium">{t("crypto.table.change7d")}</th>
            <th className="py-2 pr-3 text-right font-medium">{t("crypto.table.holdings")}</th>
            <th className="py-2 pr-3 text-right font-medium">{t("crypto.table.avgBuyPrice")}</th>
            <th className="py-2 pr-3 text-right font-medium">{t("crypto.table.profitLoss")}</th>
            <th className="py-2 pl-3 text-right font-medium">{t("crypto.table.actions")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gridline">
          {items.map((holding) => {
            const profitColor =
              holding.profit_loss === null
                ? undefined
                : Number(holding.profit_loss) > 0
                  ? "var(--success)"
                  : Number(holding.profit_loss) < 0
                    ? "var(--danger)"
                    : "var(--text-muted)";
            const sign = holding.profit_loss !== null && Number(holding.profit_loss) > 0 ? "+" : "";

            return (
              <tr
                key={holding.asset_id}
                onClick={() => onViewHistory(holding)}
                className="cursor-pointer hover:bg-surface-2"
              >
                <td className="py-3 pr-3">
                  <div className="flex items-center gap-2.5">
                    {holding.thumb_url ? (
                      <img src={holding.thumb_url} alt="" className="h-7 w-7 shrink-0 rounded-full" />
                    ) : (
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-2">
                        <Bitcoin size={14} className="text-text-secondary" />
                      </span>
                    )}
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-text-primary">{holding.name}</span>
                      <span className="block text-xs text-text-muted">{holding.symbol}</span>
                    </span>
                  </div>
                </td>
                <td className="py-3 pr-3 text-right tabular-nums text-text-primary">
                  {holding.current_price !== null
                    ? maskAmount(formatCurrency(holding.current_price), hidden)
                    : t("crypto.pendingPrice")}
                </td>
                <td className="py-3 pr-3 text-right">
                  <PercentCell value={holding.price_change_1h} />
                </td>
                <td className="py-3 pr-3 text-right">
                  <PercentCell value={holding.price_change_24h} />
                </td>
                <td className="py-3 pr-3 text-right">
                  <PercentCell value={holding.price_change_7d} />
                </td>
                <td className="py-3 pr-3 text-right">
                  <span className="block tabular-nums text-text-primary">
                    {holding.value !== null ? maskAmount(formatCurrency(holding.value), hidden) : t("crypto.pendingPrice")}
                  </span>
                  <span className="block text-xs tabular-nums text-text-muted">
                    {maskAmount(`${Number(holding.quantity)} ${holding.symbol}`, hidden)}
                  </span>
                </td>
                <td className="py-3 pr-3 text-right tabular-nums text-text-primary">
                  {holding.avg_buy_price !== null ? maskAmount(formatCurrency(holding.avg_buy_price), hidden) : "—"}
                </td>
                <td className="py-3 pr-3 text-right">
                  {holding.profit_loss !== null && holding.profit_loss_percent !== null ? (
                    <>
                      <span className="block tabular-nums" style={{ color: profitColor }}>
                        {maskAmount(`${sign}${formatCurrency(holding.profit_loss)}`, hidden)}
                      </span>
                      <span className="block text-xs tabular-nums" style={{ color: profitColor }}>
                        {sign}
                        {holding.profit_loss_percent.toFixed(2)}%
                      </span>
                    </>
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </td>
                <td className="py-3 pl-3">
                  <div className="flex justify-end gap-1">
                    <button
                      type="button"
                      aria-label={t("crypto.form.tradeButton")}
                      onClick={(event) => {
                        event.stopPropagation();
                        onTrade(holding);
                      }}
                      className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                    >
                      <Plus size={15} />
                    </button>
                    <button
                      type="button"
                      aria-label={t("common.delete")}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDelete(holding);
                      }}
                      className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
