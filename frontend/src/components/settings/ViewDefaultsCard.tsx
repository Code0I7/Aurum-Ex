import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Combobox } from "@/components/ui/Combobox";
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
            <Combobox
              id="default-range"
              className="mt-1"
              options={[
                { value: "month", label: t("dashboard.rangeMonth") },
                { value: "year", label: t("dashboard.rangeYear") },
                { value: "all", label: t("dashboard.rangeAll") },
              ]}
              value={settings.default_dashboard_range}
              onChange={(value) => update.mutate({ default_dashboard_range: value as DashboardRange })}
              placeholder={t("dashboard.rangeMonth")}
            />
          </div>

          <div>
            <Label htmlFor="default-account">{t("settings.defaultAccount")}</Label>
            <Combobox
              id="default-account"
              className="mt-1"
              options={(accounts ?? []).map((account) => ({ value: String(account.id), label: account.name }))}
              value={settings.default_account_id ? String(settings.default_account_id) : ""}
              onChange={(value) => update.mutate({ default_account_id: value ? Number(value) : null })}
              placeholder={t("settings.defaultAccountNone")}
              emptyLabel={t("settings.defaultAccountNone")}
            />
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

        {/* Считать ли данное в долг тратой. Правильного ответа нет, и
            поэтому это переключатель, а не решение автора: деньги со счёта
            ушли — значит трата; но они вернутся — значит не трата. */}
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.lending_is_spending}
            onChange={(event) => update.mutate({ lending_is_spending: event.target.checked })}
            className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
          />
          <span>
            {t("settings.lendingIsSpending")}
            <span className="block text-xs text-text-muted">
              {t("settings.lendingIsSpendingHint")}
            </span>
          </span>
        </label>

        {/* Считать ли личные вещи размещением. Та же причина, что и у
            настройки выше: правило «столько-то под риском» задумано про
            размещение, а компьютер, на котором работают, никто не
            размещал — но обесценивается и телефон. */}
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.risk_counts_personal_use}
            onChange={(event) =>
              update.mutate({ risk_counts_personal_use: event.target.checked })
            }
            className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
          />
          <span>
            {t("settings.riskCountsPersonalUse")}
            <span className="block text-xs text-text-muted">
              {t("settings.riskCountsPersonalUseHint")}
            </span>
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
