import { useState } from "react";
import { Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { NetWorthChart } from "@/components/networth/NetWorthChart";
import { AssetAllocationCard } from "@/components/networth/AssetAllocationCard";
import { CapitalRoleSummaryCard } from "@/components/networth/CapitalRoleSummaryCard";
import { RiskAllocationCard } from "@/components/networth/RiskAllocationCard";
import { AssetsTable } from "@/components/networth/AssetsTable";
import { AssetFormModal } from "@/components/networth/AssetFormModal";
import { AlertBanner } from "@/components/insights/AlertBanner";
import { useNetWorthSummary } from "@/hooks/useNetWorth";
import { useAssets, useDeleteAsset } from "@/hooks/useAssets";
import { useTranslation } from "@/lib/i18n";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { useTransactionYears } from "@/hooks/useTransactions";
import { computeRange, type CustomYearRange } from "@/lib/dateRange";
import type { Asset, NetWorthRange } from "@/types";

export function NetWorthPage() {
  const { t } = useTranslation();
  // Defaults to 5 years: a short window can show a dip whenever spending
  // briefly outpaces recorded income, which reads as decline even though
  // the long-run trend is up — 5y is long enough to make that trend visible.
  const [range, setRange] = useState<NetWorthRange>("5y");
  const now = new Date();
  const [customRange, setCustomRange] = useState<CustomYearRange>({
    fromYear: now.getFullYear(),
    toYear: now.getFullYear(),
  });
  const { data: years } = useTransactionYears();
  // Даты уходят на сервер только для своего периода: у готовых начало
  // считает сервер, и присылать ему заодно даты значило бы описать одно и
  // то же дважды, а потом гадать, что победит.
  const custom = range === "custom" ? computeRange("custom", customRange) : {};
  const { data: summary, isLoading: isSummaryLoading } = useNetWorthSummary(
    range,
    custom.startDate,
    custom.endDate
  );
  const { data: assets, isLoading: isAssetsLoading } = useAssets();
  const deleteAsset = useDeleteAsset();
  const confirm = useConfirm();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState<Asset | null>(null);

  function openCreateModal() {
    setEditingAsset(null);
    setModalOpen(true);
  }

  function openEditModal(asset: Asset) {
    setEditingAsset(asset);
    setModalOpen(true);
  }

  async function handleDelete(asset: Asset) {
    const ok = await confirm({
      message: t("netWorth.confirmDeleteAsset", { name: asset.name }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (ok) deleteAsset.mutate(asset.id);
  }

  return (
    <div className="space-y-5">
      <AlertBanner />

      <NetWorthChart
        years={years ?? [now.getFullYear()]}
        customRange={customRange}
        onCustomRangeChange={setCustomRange} summary={summary} isLoading={isSummaryLoading} range={range} onRangeChange={setRange} />

      <AssetAllocationCard breakdown={summary?.breakdown ?? []} isLoading={isSummaryLoading} />

      <CapitalRoleSummaryCard roles={summary?.capital_roles ?? []} isLoading={isSummaryLoading} />

      <RiskAllocationCard riskLevels={summary?.risk_levels ?? []} isLoading={isSummaryLoading} />

      <Card>
        <CardHeader>
          <CardTitle>{t("netWorth.myAssetsTitle")}</CardTitle>
          <Button onClick={openCreateModal}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent>
          {isAssetsLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <AssetsTable items={assets ?? []} onEdit={openEditModal} onDelete={handleDelete} />
          )}
        </CardContent>
      </Card>

      <AssetFormModal open={modalOpen} onClose={() => setModalOpen(false)} asset={editingAsset} />
    </div>
  );
}
