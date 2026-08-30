import { useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { CryptoAddModal } from "@/components/crypto/CryptoAddModal";
import { CryptoHoldingsTable } from "@/components/crypto/CryptoHoldingsTable";
import { CryptoTransactionHistoryModal } from "@/components/crypto/CryptoTransactionHistoryModal";
import { CryptoTransactionModal } from "@/components/crypto/CryptoTransactionModal";
import { useCryptoHoldings, useDeleteCryptoHolding, useRefreshCryptoPrices } from "@/hooks/useCrypto";
import { formatCurrency, getIntlLocale } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding } from "@/types";

function formatSyncedAt(iso: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}

export function CryptoPage() {
  const { t } = useTranslation();
  const { data, isLoading } = useCryptoHoldings();
  const refresh = useRefreshCryptoPrices();
  const deleteHolding = useDeleteCryptoHolding();

  const [addOpen, setAddOpen] = useState(false);
  const [tradingHolding, setTradingHolding] = useState<CryptoHolding | null>(null);
  const [historyHolding, setHistoryHolding] = useState<CryptoHolding | null>(null);

  const holdings = data?.holdings ?? [];
  const totalValue = holdings.reduce((sum, holding) => sum + (holding.value !== null ? Number(holding.value) : 0), 0);

  function handleDelete(holding: CryptoHolding) {
    if (window.confirm(t("crypto.confirmDelete", { name: holding.name }))) {
      deleteHolding.mutate(holding.asset_id);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="flex-col items-stretch gap-3 sm:flex-row sm:items-center">
          <CardTitle>{t("nav.crypto")}</CardTitle>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              <RefreshCw size={16} className={refresh.isPending ? "animate-spin" : undefined} />
              {refresh.isPending ? t("crypto.refreshing") : t("crypto.refreshButton")}
            </Button>
            <Button onClick={() => setAddOpen(true)}>
              <Plus size={16} />
              {t("crypto.addButton")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2 border-b border-border pb-4">
                <div>
                  <p className="text-xs uppercase tracking-wide text-text-muted">{t("crypto.totalValueLabel")}</p>
                  <p className="text-2xl font-semibold tabular-nums text-text-primary">{formatCurrency(totalValue)}</p>
                </div>
                <p className="text-xs text-text-muted">
                  {data?.last_synced_at
                    ? t("crypto.lastSynced", { time: formatSyncedAt(data.last_synced_at) })
                    : t("crypto.neverSynced")}
                </p>
              </div>

              {data?.error_key && <p className="mb-3 text-sm text-danger">{t(`crypto.syncError.${data.error_key}`)}</p>}

              <CryptoHoldingsTable
                items={holdings}
                onTrade={setTradingHolding}
                onViewHistory={setHistoryHolding}
                onDelete={handleDelete}
              />
            </>
          )}
        </CardContent>
      </Card>

      <CryptoAddModal open={addOpen} onClose={() => setAddOpen(false)} />
      <CryptoTransactionModal open={tradingHolding !== null} onClose={() => setTradingHolding(null)} holding={tradingHolding} />
      <CryptoTransactionHistoryModal
        open={historyHolding !== null}
        onClose={() => setHistoryHolding(null)}
        holding={historyHolding}
      />
    </div>
  );
}
