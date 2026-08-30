import { Bitcoin, Pencil, Trash2 } from "lucide-react";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding } from "@/types";

interface CryptoHoldingsListProps {
  items: CryptoHolding[];
  onEdit: (holding: CryptoHolding) => void;
  onDelete: (holding: CryptoHolding) => void;
}

export function CryptoHoldingsList({ items, onEdit, onDelete }: CryptoHoldingsListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("crypto.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((holding) => (
        <li key={holding.asset_id} className="flex items-center gap-3 py-3">
          {holding.thumb_url ? (
            <img src={holding.thumb_url} alt="" className="h-9 w-9 shrink-0 rounded-full" />
          ) : (
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-2">
              <Bitcoin size={16} className="text-text-secondary" />
            </span>
          )}
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-text-primary">{holding.name}</span>
            <span className="block truncate text-xs text-text-muted">
              {Number(holding.quantity)} {holding.symbol}
              {holding.unit_price !== null && ` · ${formatCurrency(holding.unit_price)}`}
            </span>
          </span>
          <span className="shrink-0 text-right">
            <span className="block text-sm font-medium tabular-nums text-text-primary">
              {holding.value !== null ? formatCurrency(holding.value) : t("crypto.pendingPrice")}
            </span>
          </span>
          <span className="flex shrink-0 gap-1">
            <button
              type="button"
              aria-label={t("common.edit")}
              onClick={() => onEdit(holding)}
              className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
            >
              <Pencil size={15} />
            </button>
            <button
              type="button"
              aria-label={t("common.delete")}
              onClick={() => onDelete(holding)}
              className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
            >
              <Trash2 size={15} />
            </button>
          </span>
        </li>
      ))}
    </ul>
  );
}
