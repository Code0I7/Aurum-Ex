import { Link } from "react-router-dom";
import { ExternalLink, Pencil, Trash2 } from "lucide-react";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { BudgetStatus } from "@/types";

interface BudgetListProps {
  items: BudgetStatus[];
  onEdit: (item: BudgetStatus) => void;
  onDelete: (item: BudgetStatus) => void;
}

export function BudgetList({ items, onEdit, onDelete }: BudgetListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("budget.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((item) => {
        const Icon = getCategoryIcon(item.category_icon);
        const spent = Number(item.spent);
        const limit = Number(item.monthly_limit);
        const barColor = item.is_over_budget ? "var(--danger)" : "var(--success)";
        const fillPercent = Math.min(100, item.percent);

        return (
          <li key={item.source + item.category_id} className="py-3">
            <div className="flex items-center gap-3">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                style={{ backgroundColor: `${item.category_color}26` }}
              >
                <Icon size={16} style={{ color: item.category_color }} />
              </span>
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-text-primary">
                {translateCategoryName(item.category_name)}
                {/* Откуда лимит. У строки из плана своей записи в бюджетах
                    нет: цифра приходит из «Планирования» и меняется по
                    месяцам сама. Пометка нужна, чтобы не искать, почему
                    строку не получается изменить здесь. */}
                {item.source === "plan" && (
                  <span className="ml-2 rounded px-1.5 py-0.5 align-middle text-[11px] font-normal text-text-muted ring-1 ring-border">
                    {t("budget.fromPlan")}
                  </span>
                )}
              </span>
              <span className="shrink-0 text-sm tabular-nums text-text-primary">
                {formatCurrency(spent)} <span className="text-text-muted">/ {formatCurrency(limit)}</span>
              </span>
              {/* Строка из плана правится в «Планировании», а не здесь:
                  своей записи у неё нет, и кнопка, ведущая в никуда, хуже
                  её отсутствия. Ссылка ведёт туда, где эта цифра живёт. */}
              {item.source === "plan" ? (
                <Link
                  to="/planning"
                  aria-label={t("budget.editInPlanning")}
                  title={t("budget.editInPlanning")}
                  className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                >
                  <ExternalLink size={15} />
                </Link>
              ) : (
                <span className="flex shrink-0 gap-1">
                  <button
                    type="button"
                    aria-label={t("common.edit")}
                    onClick={() => onEdit(item)}
                    className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    type="button"
                    aria-label={t("common.delete")}
                    onClick={() => onDelete(item)}
                    className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                  >
                    <Trash2 size={15} />
                  </button>
                </span>
              )}
            </div>
            <div className="mt-2 flex items-center gap-2 pl-12">
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                <span
                  className="block h-full rounded-full"
                  style={{ width: `${fillPercent}%`, backgroundColor: barColor }}
                />
              </span>
              <span className="w-10 shrink-0 text-right text-xs tabular-nums text-text-muted">
                {item.percent.toFixed(0)}%
              </span>
            </div>
            <p className="mt-1 pl-12 text-xs" style={{ color: item.is_over_budget ? "var(--danger)" : "var(--text-muted)" }}>
              {item.is_over_budget
                ? t("budget.overBy", { amount: formatCurrency(spent - limit) })
                : t("budget.remaining", { amount: formatCurrency(limit - spent) })}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
