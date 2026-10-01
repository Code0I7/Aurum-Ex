import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { useAddAssetValuation, useCreateAsset, useUpdateAsset } from "@/hooks/useAssets";
import { CURRENCIES, getCurrencyLabel } from "@/lib/currency";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { Asset, AssetClass, CapitalRole, RiskLevel } from "@/types";

interface AssetFormModalProps {
  open: boolean;
  onClose: () => void;
  asset?: Asset | null;
}

const ASSET_CLASSES: AssetClass[] = ["investments", "crypto", "real_estate", "vehicles", "precious_metals", "other"];
const CAPITAL_ROLES: CapitalRole[] = ["income", "neutral", "drain"];
const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high"];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

const EMPTY_FORM = {
  name: "",
  asset_class: "investments" as AssetClass,
  // Пусто до открытия формы: валюта установки известна только там.
  currency: "",
  value: "",
  as_of_date: todayIso(),
  notes: "",
  capital_role: "neutral" as CapitalRole,
  monthly_cash_flow: "",
  risk_level: "medium" as RiskLevel,
  is_personal_use: false,
};

export function AssetFormModal({ open, onClose, asset }: AssetFormModalProps) {
  const { t, language, currency: installCurrency } = useTranslation();
  const createAsset = useCreateAsset();
  const updateAsset = useUpdateAsset();
  const addValuation = useAddAssetValuation();

  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (asset) {
      setForm({
        name: asset.name,
        asset_class: asset.asset_class,
        currency: asset.currency,
        value: asset.current_value,
        as_of_date: todayIso(),
        notes: asset.notes ?? "",
        capital_role: asset.capital_role,
        monthly_cash_flow: asset.monthly_cash_flow ?? "",
        risk_level: asset.risk_level,
        is_personal_use: asset.is_personal_use,
      });
    } else {
      // У нового актива валюта установки. Имущество за границей бывает, но
      // это редкий случай, а не умолчание: раньше здесь молча стоял
      // доллар, и на рублёвой установке актив не попадал в капитал вовсе.
      setForm({ ...EMPTY_FORM, currency: installCurrency });
    }
    setError(null);
  }, [open, asset, installCurrency]);

  const isSaving = createAsset.isPending || updateAsset.isPending || addValuation.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    try {
      if (asset) {
        await updateAsset.mutateAsync({
          id: asset.id,
          input: {
            name: form.name,
            asset_class: form.asset_class,
            currency: form.currency,
            notes: form.notes || null,
            capital_role: form.capital_role,
            monthly_cash_flow: form.monthly_cash_flow || null,
            risk_level: form.risk_level,
            is_personal_use: form.is_personal_use,
          },
        });
        if (form.value !== asset.current_value) {
          await addValuation.mutateAsync({ id: asset.id, input: { value: form.value, as_of_date: form.as_of_date } });
        }
      } else {
        await createAsset.mutateAsync({
          name: form.name,
          asset_class: form.asset_class,
          currency: form.currency,
          value: form.value,
          as_of_date: form.as_of_date,
          notes: form.notes || null,
          capital_role: form.capital_role,
          monthly_cash_flow: form.monthly_cash_flow || null,
          risk_level: form.risk_level,
          is_personal_use: form.is_personal_use,
        });
      }
      onClose();
    } catch {
      setError(t("netWorth.form.saveError"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={asset ? t("netWorth.form.editTitle") : t("netWorth.form.newTitle")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="asset-name">{t("netWorth.form.nameLabel")}</Label>
          <Input
            id="asset-name"
            required
            placeholder={t("netWorth.form.namePlaceholder")}
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="asset-class">{t("netWorth.form.classLabel")}</Label>
          <Select
            id="asset-class"
            value={form.asset_class}
            onChange={(event) => setForm((prev) => ({ ...prev, asset_class: event.target.value as AssetClass }))}
          >
            {ASSET_CLASSES.map((value) => (
              <option key={value} value={value}>
                {t(`netWorth.assetClass.${value}` as TranslationKey)}
              </option>
            ))}
          </Select>
        </div>

        {/* Валюта актива. Капитал считается в одной валюте и ничего не
            переводит, поэтому от неё зависит, в какую колонку актив
            попадёт, — и выбирать её должен человек, а не умолчание. */}
        <div>
          <Label htmlFor="asset-currency">{t("netWorth.form.currencyLabel")}</Label>
          <Select
            id="asset-currency"
            value={form.currency}
            onChange={(event) => setForm((prev) => ({ ...prev, currency: event.target.value }))}
          >
            {CURRENCIES.map((option) => (
              <option key={option.code} value={option.code}>
                {getCurrencyLabel(option.code, language)}
              </option>
            ))}
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="asset-value">
              {asset ? t("netWorth.form.currentValueLabel") : t("netWorth.form.valueLabel")}
            </Label>
            <Input
              id="asset-value"
              type="number"
              step="0.01"
              min="0"
              required
              value={form.value}
              onChange={(event) => setForm((prev) => ({ ...prev, value: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="asset-date">{t("netWorth.form.dateLabel")}</Label>
            <Input
              id="asset-date"
              type="date"
              required
              value={form.as_of_date}
              onChange={(event) => setForm((prev) => ({ ...prev, as_of_date: event.target.value }))}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="asset-role">{t("netWorth.form.roleLabel")}</Label>
          <Select
            id="asset-role"
            value={form.capital_role}
            onChange={(event) => setForm((prev) => ({ ...prev, capital_role: event.target.value as CapitalRole }))}
          >
            {CAPITAL_ROLES.map((value) => (
              <option key={value} value={value}>
                {t(`netWorth.capitalRole.${value}` as TranslationKey)}
              </option>
            ))}
          </Select>
          <p className="mt-1 text-xs text-text-muted">
            {t(`netWorth.capitalRoleFormHint.${form.capital_role}` as TranslationKey)}
          </p>
        </div>

        <div>
          <Label htmlFor="asset-risk">{t("netWorth.form.riskLevelLabel")}</Label>
          <Select
            id="asset-risk"
            value={form.risk_level}
            onChange={(event) => setForm((prev) => ({ ...prev, risk_level: event.target.value as RiskLevel }))}
          >
            {RISK_LEVELS.map((value) => (
              <option key={value} value={value}>
                {t(`netWorth.riskLevel.${value}` as TranslationKey)}
              </option>
            ))}
          </Select>
          <p className="mt-1 text-xs text-text-muted">
            {t(`netWorth.riskLevelFormHint.${form.risk_level}` as TranslationKey)}
          </p>
        </div>

        <div>
          <Label htmlFor="asset-cash-flow">{t("netWorth.form.cashFlowLabel")}</Label>
          <Input
            id="asset-cash-flow"
            type="number"
            step="0.01"
            placeholder={t("netWorth.form.cashFlowPlaceholder")}
            value={form.monthly_cash_flow}
            onChange={(event) => setForm((prev) => ({ ...prev, monthly_cash_flow: event.target.value }))}
          />
          <p className="mt-1 text-xs text-text-muted">{t("netWorth.form.cashFlowHint")}</p>
        </div>

        <div>
          <Label htmlFor="asset-notes">{t("netWorth.form.notesLabel")}</Label>
          <Input
            id="asset-notes"
            value={form.notes}
            onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))}
          />
        </div>

        <label className="flex cursor-pointer items-start gap-2 text-sm">

          <input

            type="checkbox"

            checked={form.is_personal_use}

            onChange={(event) => setForm((prev) => ({ ...prev, is_personal_use: event.target.checked }))}

            className="mt-0.5 h-3.5 w-3.5 accent-text-primary"

          />

          <span>

            {t("netWorth.personalUse")}

            <span className="block text-xs text-text-muted">{t("netWorth.personalUseHint")}</span>

          </span>

        </label>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
