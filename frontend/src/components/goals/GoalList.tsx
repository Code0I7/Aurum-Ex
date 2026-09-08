import { CheckCircle2, Flag, PiggyBank, Pencil, RotateCcw, Trash2, XCircle } from "lucide-react";
import { formatCurrency, getIntlLocale } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { Goal, GoalStatus } from "@/types";

interface GoalListProps {
  items: Goal[];
  onContribute: (goal: Goal) => void;
  onEdit: (goal: Goal) => void;
  onDelete: (goal: Goal) => void;
  /** Завершить цель или вернуть её в работу. */
  onStatusChange: (goal: Goal, status: GoalStatus) => void;
}

function formatTargetDate(isoDate: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { day: "numeric", month: "short", year: "numeric" }).format(
    new Date(`${isoDate}T00:00:00`)
  );
}

export function GoalList({ items, onContribute, onEdit, onDelete, onStatusChange }: GoalListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("goal.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((goal) => {
        const current = Number(goal.current_amount);
        const target = Number(goal.target_amount);
        const remaining = Number(goal.remaining);
        const isClosed = goal.status !== "active";
        // Полоса делится на «до цели» и «сверх». Рисовать 140% одной
        // заливкой нельзя — она упрётся в край и будет неотличима от ровно
        // достигнутой; отдельный кусок показывает, что накоплено больше.
        const fillPercent = Math.min(100, goal.percent);
        const overPercent = goal.percent > 100 ? Math.min(60, goal.percent - 100) : 0;

        return (
          <li key={goal.id} className="py-3">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-2">
                <Flag size={16} className="text-text-secondary" />
              </span>
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-text-primary">
                {goal.name}
                {goal.by_account.length > 0 && (
                  <span className="block truncate text-xs font-normal text-text-muted">
                    {goal.by_account
                      .map((part) => `${part.account_name} · ${formatCurrency(part.amount)}`)
                      .join(" · ")}
                  </span>
                )}
              </span>
              <span className="shrink-0 text-sm tabular-nums text-text-primary">
                {formatCurrency(current)} <span className="text-text-muted">/ {formatCurrency(target)}</span>
              </span>
              <span className="flex shrink-0 gap-1">
                {isClosed ? (
                  <button
                    type="button"
                    aria-label={t("goal.reopen")}
                    title={t("goal.reopen")}
                    onClick={() => onStatusChange(goal, "active")}
                    className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                  >
                    <RotateCcw size={15} />
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      aria-label={t("goal.contributeLabel")}
                      onClick={() => onContribute(goal)}
                      className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-success"
                    >
                      <PiggyBank size={15} />
                    </button>
                    {/* Два разных конца, а не один. Деньги ушли на то, ради
                        чего копились, — это одно; передумали и вернули —
                        совсем другое, и в исходной таблице их различал
                        только текст комментария. */}
                    <button
                      type="button"
                      aria-label={t("goal.markAchieved")}
                      title={t("goal.markAchieved")}
                      onClick={() => onStatusChange(goal, "achieved")}
                      className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-success"
                    >
                      <CheckCircle2 size={15} />
                    </button>
                    <button
                      type="button"
                      aria-label={t("goal.markCancelled")}
                      title={t("goal.markCancelled")}
                      onClick={() => onStatusChange(goal, "cancelled")}
                      className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                    >
                      <XCircle size={15} />
                    </button>
                  </>
                )}
                <button
                  type="button"
                  aria-label={t("common.edit")}
                  onClick={() => onEdit(goal)}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                >
                  <Pencil size={15} />
                </button>
                <button
                  type="button"
                  aria-label={t("common.delete")}
                  onClick={() => onDelete(goal)}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                >
                  <Trash2 size={15} />
                </button>
              </span>
            </div>
            <div className="mt-2 flex items-center gap-2 pl-12">
              <span className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                <span
                  className={`block h-full ${isClosed ? "bg-text-muted" : "bg-success"}`}
                  style={{ width: `${fillPercent}%` }}
                />
                {overPercent > 0 && (
                  <span
                    className="block h-full bg-accent"
                    style={{ width: `${overPercent}%` }}
                    title={t("goal.overTarget", {
                      amount: formatCurrency(current - target),
                    })}
                  />
                )}
              </span>
              <span className="w-10 shrink-0 text-right text-xs tabular-nums text-text-muted">
                {goal.percent.toFixed(0)}%
              </span>
            </div>
            <p
              className="mt-1 pl-12 text-xs"
              style={{ color: goal.is_reached && !isClosed ? "var(--success)" : "var(--text-muted)" }}
            >
              {isClosed
                ? t(goal.status === "achieved" ? "goal.closedAchieved" : "goal.closedCancelled", {
                    date: goal.closed_at ? formatTargetDate(goal.closed_at) : "—",
                    // У завершённой цели показывается внесённое, а не
                    // остаток: остаток там ноль, потому что накопленное
                    // потрачено, и «накоплено 0 ₽» — не ответ.
                    amount: formatCurrency(goal.deposited),
                  })
                : goal.is_reached
                ? t("goal.reached")
                : goal.target_date
                  ? t("goal.remainingWithDate", { amount: formatCurrency(remaining), date: formatTargetDate(goal.target_date) })
                  : t("goal.remaining", { amount: formatCurrency(remaining) })}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
