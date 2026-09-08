import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency } from "@/lib/format";
import { useReservations } from "@/hooks/useGoals";
import { useNetWorthSummary } from "@/hooks/useNetWorth";
import type { AccountReservation, DashboardAccountBalance } from "@/types";

/**
 * Остатки по счетам — «сколько у меня сейчас и где».
 *
 * Всегда текущие, независимо от выбранного сверху периода: вопрос от периода
 * не зависит, и подменять ответ остатком на конец марта значило бы врать
 * ровно тому, кто открыл дашборд, чтобы понять, сколько у него денег.
 */
export function AccountBalancesCard({ accounts }: { accounts: DashboardAccountBalance[] }) {
  const { t } = useTranslation();
  const { data: reservations } = useReservations();
  // Быстрые деньги показываются здесь, а не только на вкладке капитала:
  // обзор открывают первым, и вопрос «сколько я могу потратить» задают
  // раньше, чем «сколько я стою». Период короткий — само число от него
  // не зависит, берётся текущее состояние.
  const { data: netWorth } = useNetWorthSummary("30d");

  if (accounts.length === 0) return null;

  const byAccount = new Map<number, AccountReservation[]>();
  for (const item of reservations ?? []) {
    const list = byAccount.get(item.account_id);
    if (list) list.push(item);
    else byAccount.set(item.account_id, [item]);
  }

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
        <span className="shrink-0 text-right">
          <span className="block text-lg font-semibold tabular-nums">{formatCurrency(total)}</span>
          {netWorth && (
            <span className="block text-xs text-text-muted">
              {t("netWorth.liquid")}:{" "}
              <span className="tabular-nums">{formatCurrency(netWorth.liquid)}</span>
            </span>
          )}
        </span>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-gridline">
          {accounts.map((account) => {
            const balance = Number(account.balance);
            const reserved = Number(account.reserved);
            return (
              <li key={account.account_id} className="py-2">
                <div className="flex items-center justify-between gap-3">
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
                </div>
                <AccountBar
                  balance={balance}
                  segments={byAccount.get(account.account_id) ?? []}
                  freeLabel={t("dashboard.freeSegment")}
                />
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

/**
 * Полоса остатка: свободное одним куском, отложенное — отдельными.
 *
 * Смысл в том, чтобы отложенное было видно как часть счёта, а не как
 * отдельная сумма где-то ещё. Деньги никуда не перекладывались: это тот же
 * остаток, часть которого обещана другой задаче.
 *
 * Отрезков нет — нет и полосы: у большинства счетов резерва не бывает, и
 * ровная зелёная черта под каждой строкой была бы украшением без смысла.
 *
 * Сверх остатка отрезки не рисуются: отложить больше, чем лежит на счёте,
 * нельзя, и доля считается от самого остатка.
 */
function AccountBar({
  balance,
  segments,
  freeLabel,
}: {
  balance: number;
  segments: AccountReservation[];
  freeLabel: string;
}) {
  if (segments.length === 0 || balance <= 0) return null;

  const reserved = segments.reduce((sum, item) => sum + Number(item.amount), 0);
  const free = Math.max(0, balance - reserved);

  return (
    <span className="mt-1.5 flex h-1.5 overflow-hidden rounded-full bg-surface-2" role="presentation">
      <span
        className="block h-full bg-success/70 transition-[width]"
        style={{ width: `${(free / balance) * 100}%` }}
        title={`${freeLabel}: ${formatCurrency(free)}`}
      />
      {segments.map((item) => (
        <span
          key={item.goal_id}
          // Золотом, а не цветом цели: цвет у целей не задаётся, а
          // придумывать его по номеру значило бы, что один и тот же
          // отрезок меняет цвет при добавлении соседней цели.
          className="block h-full border-l border-surface-1 bg-accent transition-[width] hover:brightness-125"
          style={{ width: `${(Number(item.amount) / balance) * 100}%` }}
          title={`${item.goal_name}: ${formatCurrency(item.amount)}`}
        />
      ))}
    </span>
  );
}
