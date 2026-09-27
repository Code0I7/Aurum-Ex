import { Link } from "react-router-dom";
import { ArrowRight, Target } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { AccountReservation, DashboardAccountBalance } from "@/types";

/**
 * Подробности счёта: сколько всего, сколько отложено, сколько можно тратить,
 * и на какие цели отложено.
 *
 * Открывается нажатием на строку счёта. До этого то же самое можно было
 * узнать только наведением на отрезок полосы — на телефоне, где наведения
 * нет, отрезок в полтора миллиметра оставался неопрашиваемым, а строка
 * «отложено … доступно …» не говорила, на что именно отложено.
 *
 * Отсюда же переходы: к самой цели и к операциям этого счёта — вопрос
 * «а что там» возникает сразу за вопросом «сколько там».
 */
export function AccountDetailsModal({
  account,
  reservations,
  onClose,
}: {
  /** Счёт, по которому открыты подробности. Null — окно закрыто. */
  account: DashboardAccountBalance | null;
  /** Отложенное по целям на этом счёте. */
  reservations: AccountReservation[];
  onClose: () => void;
}) {
  const { t, currency: base } = useTranslation();
  const balance = Number(account?.balance ?? 0);
  const reserved = Number(account?.reserved ?? 0);

  return (
    <Dialog open={account !== null} onClose={onClose} title={account?.name ?? ""}>
      {account && (
        <div className="space-y-4">
          <div className="divide-y divide-gridline">
            <Figure
              label={t("dashboard.accountTotal")}
              value={formatCurrency(balance, account.currency)}
              extra={
                account.currency === base
                  ? undefined
                  : `≈ ${formatCurrency(account.balance_base, base)}`
              }
              // Минус — это долг по карте, и он красный так же, как в списке.
              color={balance < 0 ? "var(--danger)" : undefined}
            />
            {reserved > 0 && (
              <>
                <Figure
                  label={t("dashboard.accountReserved")}
                  value={formatCurrency(reserved, account.currency)}
                  color="var(--accent)"
                />
                <Figure
                  label={t("dashboard.accountAvailable")}
                  value={formatCurrency(account.available, account.currency)}
                />
              </>
            )}
          </div>

          {/* На что отложено. Деньги никуда не перекладывались: это тот же
              остаток, часть которого обещана другой задаче. */}
          {reservations.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium text-text-muted">
                {t("dashboard.accountReservedFor")}
              </p>
              <ul className="divide-y divide-gridline">
                {reservations.map((item) => (
                  <li key={item.goal_id}>
                    {/* Ссылка на саму цель: она открывает её историю
                        накопления — то, что спрашивают следом. */}
                    <Link
                      to={`/goals?goal=${item.goal_id}`}
                      onClick={onClose}
                      className="flex items-center justify-between gap-3 py-2 text-sm hover:text-text-primary"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <Target size={14} className="shrink-0 text-accent" />
                        <span className="truncate">{item.goal_name}</span>
                      </span>
                      <span className="shrink-0 tabular-nums">
                        {formatCurrency(item.amount, account.currency)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap gap-2 border-t border-gridline pt-3 text-sm">
            <Link
              to={`/transactions?account=${account.account_id}`}
              onClick={onClose}
              className="inline-flex items-center gap-1 rounded-lg bg-surface-2 px-3 py-1.5 text-text-primary hover:opacity-90"
            >
              {t("dashboard.accountTransactions")}
              <ArrowRight size={14} />
            </Link>
            {reservations.length > 0 && (
              <Link
                to="/goals"
                onClick={onClose}
                className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-text-secondary hover:bg-surface-2"
              >
                {t("nav.goals")}
                <ArrowRight size={14} />
              </Link>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}

function Figure({
  label,
  value,
  extra,
  color,
}: {
  label: string;
  value: string;
  extra?: string;
  color?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2 first:pt-0">
      <span className="text-sm text-text-muted">{label}</span>
      <span className="text-right">
        <span className="block font-medium tabular-nums" style={color ? { color } : undefined}>
          {value}
        </span>
        {extra && <span className="block text-xs text-text-muted tabular-nums">{extra}</span>}
      </span>
    </div>
  );
}
