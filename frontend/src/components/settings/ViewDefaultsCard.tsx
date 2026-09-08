import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { useAppSettings, useUpdateAppSettings } from "@/hooks/useSettings";
import { useAccounts } from "@/hooks/useAccounts";
import { useTranslation } from "@/lib/i18n";
import type { DashboardRange } from "@/types";

/**
 * Что показывать при открытии приложения.
 *
 * Хранится на сервере, а не в браузере: установка однопользовательская, и
 * выбор, сделанный на ноутбуке, должен действовать с телефона. Переключатели
 * на самих страницах остаются — они временные, для этого экрана и этого
 * браузера, и перекрывают настройку до конца сеанса.
 */
export function ViewDefaultsCard() {
  const { t } = useTranslation();
  const { data: settings } = useAppSettings();
  const update = useUpdateAppSettings();
  const { data: accounts } = useAccounts(false);

  if (!settings) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.viewDefaults")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-xs text-text-muted">{t("settings.viewDefaultsHint")}</p>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="default-range">{t("settings.defaultRange")}</Label>
            <select
              id="default-range"
              value={settings.default_dashboard_range}
              onChange={(event) =>
                update.mutate({ default_dashboard_range: event.target.value as DashboardRange })
              }
              className="mt-1 w-full rounded-md border border-border bg-surface-1 px-3 py-2 text-sm"
            >
              <option value="month">{t("dashboard.rangeMonth")}</option>
              <option value="year">{t("dashboard.rangeYear")}</option>
              <option value="all">{t("dashboard.rangeAll")}</option>
            </select>
          </div>

          <div>
            <Label htmlFor="default-account">{t("settings.defaultAccount")}</Label>
            <select
              id="default-account"
              value={settings.default_account_id ?? ""}
              onChange={(event) =>
                update.mutate({
                  default_account_id: event.target.value ? Number(event.target.value) : null,
                })
              }
              className="mt-1 w-full rounded-md border border-border bg-surface-1 px-3 py-2 text-sm"
            >
              <option value="">{t("settings.defaultAccountNone")}</option>
              {(accounts ?? []).map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-text-muted">{t("settings.defaultAccountHint")}</p>
          </div>

          <div>
            <Label htmlFor="default-page-size">{t("settings.defaultPageSize")}</Label>
            <Input
              id="default-page-size"
              type="number"
              min={10}
              max={500}
              step={10}
              defaultValue={settings.default_page_size}
              // Сохраняем по уходу из поля, а не на каждое нажатие: иначе
              // «50» по пути к «500» успело бы стать магазкой и перезагрузить
              // список дважды.
              onBlur={(event) => {
                const value = Number(event.target.value);
                if (value >= 10 && value <= 500 && value !== settings.default_page_size) {
                  update.mutate({ default_page_size: value });
                }
              }}
            />
            <p className="mt-1 text-xs text-text-muted">{t("settings.defaultPageSizeHint")}</p>
          </div>
        </div>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.show_cents}
            onChange={(event) => update.mutate({ show_cents: event.target.checked })}
            className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
          />
          <span>
            {t("settings.showCents")}
            <span className="block text-xs text-text-muted">{t("settings.showCentsHint")}</span>
          </span>
        </label>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.group_repeats_by_default}
            onChange={(event) => update.mutate({ group_repeats_by_default: event.target.checked })}
            className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
          />
          <span>
            {t("settings.groupRepeats")}
            <span className="block text-xs text-text-muted">{t("settings.groupRepeatsHint")}</span>
          </span>
        </label>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.day_dividers_by_default}
            onChange={(event) => update.mutate({ day_dividers_by_default: event.target.checked })}
            className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
          />
          <span>
            {t("settings.dayDividers")}
            <span className="block text-xs text-text-muted">{t("settings.dayDividersHint")}</span>
          </span>
        </label>
      </CardContent>
    </Card>
  );
}
