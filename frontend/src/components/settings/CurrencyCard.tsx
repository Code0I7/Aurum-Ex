import { useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Select } from "@/components/ui/Input";
import { useTranslation } from "@/lib/i18n";
import { CURRENCIES, getCurrencyLabel } from "@/lib/currency";
import { useAppSettings, useUpdateAppSettings } from "@/hooks/useSettings";
import {
  useAddWatchedCurrency,
  useBackfillRates,
  useRates,
  useRemoveWatchedCurrency,
  useSyncRates,
} from "@/hooks/useCurrencies";

export function CurrencyCard() {
  const { t, language } = useTranslation();
  const { data: settings, isLoading } = useAppSettings();
  const updateSettings = useUpdateAppSettings();

  const { data: rates } = useRates();
  const addCurrency = useAddWatchedCurrency();
  const removeCurrency = useRemoveWatchedCurrency();
  const sync = useSyncRates();
  const backfill = useBackfillRates();

  const [adding, setAdding] = useState("");

  const watched = rates ?? [];
  // Валюту установки в список не предлагаем: её курс к самой себе всегда
  // единица, и строка про это отвечает на вопрос, которого никто не задавал.
  const known = new Set([settings?.currency, ...watched.map((row) => row.code)]);
  const available = CURRENCIES.filter((option) => !known.has(option.code));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.currency")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <Select
            value={settings?.currency ?? ""}
            disabled={isLoading || updateSettings.isPending}
            onChange={(event) => updateSettings.mutate({ currency: event.target.value })}
            className="max-w-xs"
          >
            {CURRENCIES.map((currency) => (
              <option key={currency.code} value={currency.code}>
                {getCurrencyLabel(currency.code, language)}
              </option>
            ))}
          </Select>
          <p className="text-xs text-text-muted">{t("settings.currencyHint")}</p>
        </div>

        {/* Список наблюдения. Валюта счёта попадает в него сама и убрана
            быть не может: её курс нужен расчётам, и перестать его загружать
            значило бы тихо испортить итоги. */}
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("settings.watchlist")}</p>
          <div className="flex flex-wrap gap-1.5">
            {watched.length === 0 && (
              <p className="text-xs text-text-muted">{t("settings.watchlistEmpty")}</p>
            )}
            {watched.map((row) => (
              <span
                key={row.code}
                className="inline-flex items-center gap-1 rounded-md bg-surface-2 py-1 pl-2 pr-1 text-xs"
              >
                {row.code}
                <button
                  type="button"
                  onClick={() => removeCurrency.mutate(row.code)}
                  disabled={row.in_use || removeCurrency.isPending}
                  aria-label={t("settings.watchlistRemove", { code: row.code })}
                  title={
                    row.in_use
                      ? t("settings.watchlistInUse")
                      : t("settings.watchlistRemove", { code: row.code })
                  }
                  className="rounded p-0.5 text-text-muted hover:bg-surface-1 hover:text-danger disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={adding}
              onChange={(event) => setAdding(event.target.value)}
              className="max-w-xs flex-1"
            >
              <option value="">{t("settings.watchlistPick")}</option>
              {available.map((option) => (
                <option key={option.code} value={option.code}>
                  {getCurrencyLabel(option.code, language)}
                </option>
              ))}
            </Select>
            <Button
              type="button"
              variant="secondary"
              disabled={!adding || addCurrency.isPending}
              onClick={() => addCurrency.mutate(adding, { onSuccess: () => setAdding("") })}
            >
              {t("settings.watchlistAdd")}
            </Button>
          </div>
          <p className="text-xs text-text-muted">{t("settings.watchlistHint")}</p>
        </div>

        {/* Загрузка курсов. Две кнопки, и разница между ними важна: первая
            берёт сегодняшний курс, вторая идёт назад по датам операций,
            которым курса не хватило, и возвращает их в расчёты. */}
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("settings.rates")}</p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={sync.isPending}
              onClick={() => sync.mutate()}
            >
              {sync.isPending ? t("settings.ratesSyncing") : t("settings.ratesSync")}
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={backfill.isPending}
              onClick={() => backfill.mutate()}
            >
              {backfill.isPending ? t("settings.ratesSyncing") : t("settings.ratesBackfill")}
            </Button>
          </div>

          {(sync.isError || backfill.isError) && (
            <p className="text-xs text-danger">{t("settings.ratesError")}</p>
          )}
          {sync.isSuccess && (
            <p className="text-xs text-text-muted">
              {t("settings.ratesSyncResult", {
                saved: sync.data.saved,
                recomputed: sync.data.recomputed,
              })}
            </p>
          )}
          {backfill.isSuccess && (
            <p className="text-xs text-text-muted">
              {t("settings.ratesBackfillResult", {
                dates: backfill.data.dates,
                recomputed: backfill.data.recomputed,
                remaining: backfill.data.remaining,
              })}
            </p>
          )}
          <p className="text-xs text-text-muted">{t("settings.ratesHint")}</p>
        </div>
      </CardContent>
    </Card>
  );
}
