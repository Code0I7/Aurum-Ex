import { CheckCircle2, Flag, PiggyBank, Pencil, RotateCcw, Trash2, XCircle } from "lucide-react";
import { formatCurrency, getIntlLocale, pluralizeRu } from "@/lib/format";
import { useTranslation, type Language } from "@/lib/i18n";
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
        // У завершённой цели считается ВНЕСЁННОЕ, а не остаток. Остаток
        // там ноль: накопленное потрачено, и перенос старой таблицы
        // записывал эту трату возвратом. Полоса из-за этого показывала
        // «0 из 1790» и пустой прогресс у цели, на которую копили полгода.
        const shown = isClosed ? Number(goal.deposited) : current;
        const percent = target ? (shown / target) * 100 : 0;
        // Полоса делится на «до цели» и «сверх». Рисовать 140% одной
        // заливкой нельзя — она упрётся в край и будет неотличима от ровно
        // достигнутой; отдельный кусок показывает, что накоплено больше.
        const fillPercent = Math.min(100, percent);
        const overPercent = percent > 100 ? Math.min(60, percent - 100) : 0;

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
                {formatCurrency(shown)} <span className="text-text-muted">/ {formatCurrency(target)}</span>
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
                      amount: formatCurrency(shown - target),
                    })}
                  />
                )}
              </span>
              <span className="w-10 shrink-0 text-right text-xs tabular-nums text-text-muted">
                {percent.toFixed(0)}%
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
                    amount: formatCurrency(shown),
                  })
                : goal.is_reached
                  ? t("goal.reached")
                  : t("goal.remaining", { amount: formatCurrency(remaining) })}
            </p>

            {/* Три числа из трёх дат — отдельной строкой, серым.

                Раньше дата стояла в одной строке с остатком и с предлогом
                «до», то есть читалась сроком. Заполняли её началом
                накопления, и строка говорила обратное тому, что в ней
                записано. Теперь даты не показываются вовсе: показывается
                то, ради чего их заводили, — сколько копим, сколько
                осталось до плана и за сколько собрали. */}
            <GoalDays goal={goal} />
          </li>
        );
      })}
    </ul>
  );
}


/** «3 дня», «15 дней» — по-русски с согласованием, по-английски без. */
function daysLabel(days: number, language: Language): string {
  const value = Math.abs(days);
  if (language !== "ru") return `${value} ${value === 1 ? "day" : "days"}`;
  return `${value} ${pluralizeRu(value, "день", "дня", "дней")}`;
}

/**
 * Сколько копим, сколько осталось до плана, за сколько собрали.
 *
 * Ни одно из трёх не показывается, когда считать не из чего: даты
 * необязательны, и прочерк вместо числа сообщал бы только то, что поле не
 * заполнено, — а это и так видно по форме.
 */
function GoalDays({ goal }: { goal: Goal }) {
  const { t, language } = useTranslation();

  const parts: string[] = [];
  if (goal.days_taken !== null) {
    parts.push(t("goal.daysTaken", { days: daysLabel(goal.days_taken, language) }));
  } else if (goal.days_saving !== null) {
    parts.push(t("goal.daysSaving", { days: daysLabel(goal.days_saving, language) }));
  }
  if (goal.days_to_plan !== null) {
    // Просрочка — это не ошибка, а обычная жизнь накопления, и говорится
    // о ней тем же серым, что и всё остальное.
    parts.push(
      t(goal.days_to_plan < 0 ? "goal.daysOverdue" : "goal.daysToPlan", {
        days: daysLabel(goal.days_to_plan, language),
      })
    );
  }

  if (parts.length === 0) return null;
  return <p className="mt-0.5 pl-12 text-xs text-text-muted">{parts.join(" · ")}</p>;
}
