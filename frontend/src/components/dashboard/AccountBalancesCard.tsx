import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency } from "@/lib/format";
import type { DashboardAccountBalance } from "@/types";

/**
 * Остатки по счетам — «сколько у меня сейчас и где».
 *
 * Всегда текущие, независимо от выбранного сверху периода: вопрос от периода
 * не зависит, и подменять ответ остатком на конец марта значило бы врать
 * ровно тому, кто открыл дашборд, чтобы понять, сколько у него денег.
 */
export function AccountBalancesCard({ accounts }: { accounts: DashboardAccountBalance[] }) {
  const { t } = useTranslation();

  if (accounts.length === 0) return null;

  const total = accounts
    .filter((account) => account.nature === "asset")
    .reduce((sum, account) => sum + Number(account.balance), 0);

  return (
    <Card>
      <CardHeader className="items-start">
        <div>
          <CardTitle>{t("dashboard.accountsTitle")}</CardTitle>
          <p className="mt-1 text-xs text-text-muted">{t("dashboard.accountsHint")}</p>
        </div>
        <span className="shrink-0 text-lg font-semibold tabular-nums">{formatCurrency(total)}</span>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-gridline">
          {accounts.map((account) => {
            const balance = Number(account.balance);
            const reserved = Number(account.reserved);
            return (
              <li key={account.account_id} className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0">
                  <span className="block truncate text-sm">{account.name}</span>
                  {/* Отложенное дописывается второй строкой только когда оно
                      есть: у большинства счетов резерва нет, и пустая строка
                      растянула бы список без пользы. */}
                  {reserved > 0 && (
                    <span className="block text-xs text-text-muted">
                      {t("dashboard.reservedAvailable", {
                        reserved: formatCurrency(reserved),
                        available: formatCurrency(account.available),
                      })}
                    </span>
                  )}
                </span>
                <span
                  className="shrink-0 text-sm font-medium tabular-nums"
                  style={{ color: balance < 0 ? "var(--danger)" : "var(--text-primary)" }}
                >
                  {formatCurrency(balance)}
                </span>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
