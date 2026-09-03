import { Pencil, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import type { CryptoPortfolio } from "@/types";

interface CryptoPortfolioTabsProps {
  portfolios: CryptoPortfolio[];
  activeId: number | null;
  onChange: (id: number | null) => void;
  onAdd: () => void;
  onEdit: (portfolio: CryptoPortfolio) => void;
}

/** Horizontally-scrolling pill row (no wrap) so a long list of portfolios
 * stays usable on a phone screen instead of pushing the rest of the tab
 * down. "All" plus one pill per portfolio, a pencil to edit whichever one
 * is active, and a dashed "+" pill to create another. */
export function CryptoPortfolioTabs({ portfolios, activeId, onChange, onAdd, onEdit }: CryptoPortfolioTabsProps) {
  const { t } = useTranslation();
  const active = portfolios.find((p) => p.id === activeId) ?? null;

  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
      <button
        type="button"
        onClick={() => onChange(null)}
        className={cn(
          "shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
          activeId === null
            ? "border-series-1 bg-surface-2 text-text-primary"
            : "border-border text-text-muted hover:text-text-primary"
        )}
      >
        {t("crypto.portfolio.all")}
      </button>
      {portfolios.map((portfolio) => {
        const isActive = portfolio.id === activeId;
        return (
          <button
            key={portfolio.id}
            type="button"
            onClick={() => onChange(portfolio.id)}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
              isActive
                ? "border-series-1 bg-surface-2 text-text-primary"
                : "border-border text-text-muted hover:text-text-primary"
            )}
          >
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: portfolio.color ?? "var(--text-muted)" }}
            />
            {portfolio.name}
          </button>
        );
      })}
      {active && (
        <button
          type="button"
          aria-label={t("common.edit")}
          onClick={() => onEdit(active)}
          className="shrink-0 rounded-full p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
        >
          <Pencil size={13} />
        </button>
      )}
      <button
        type="button"
        aria-label={t("crypto.portfolio.addLabel")}
        onClick={onAdd}
        className="shrink-0 rounded-full border border-dashed border-border p-1.5 text-text-muted hover:border-series-1 hover:text-text-primary"
      >
        <Plus size={13} />
      </button>
    </div>
  );
}
