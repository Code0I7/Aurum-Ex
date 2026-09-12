import { ArrowLeftRight, CalendarSearch, Pencil, SquareDivide, Trash2 } from "lucide-react";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import { amountColorClass, amountSign } from "@/lib/transactionAmount";
import { useTranslation } from "@/lib/i18n";
import { categoryPath, translateCategoryName } from "@/lib/categoryLabels";
import { useCategories } from "@/hooks/useCategories";
import type { Transaction } from "@/types";

interface TransactionsTableProps {
  items: Transaction[];
  onEdit: (transaction: Transaction) => void;
  onDelete: (transaction: Transaction) => void;
  /** Present only while showing search results, which span every month —
   * lets a row's date carry the year and offers a way to jump back to
   * browsing that transaction's month instead of just listing it flat. */
  onJumpToMonth?: (transaction: Transaction) => void;
}

export function TransactionsTable({ items, onEdit, onDelete, onJumpToMonth }: TransactionsTableProps) {
  const { t, currency: base } = useTranslation();
  const { data: categories } = useCategories();

  if (items.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-text-muted">
        {onJumpToMonth ? t("transactions.searchNoneFound") : t("transactions.noneFound")}
      </p>
    );
  }

  return (
    <>
      <ul className="divide-y divide-gridline">
        {items.map((tx) => {
          const isTransfer = tx.type === "transfer";
          const isSplit = tx.splits.length > 0;
          const Icon = isTransfer ? ArrowLeftRight : isSplit ? SquareDivide : getCategoryIcon(tx.category?.icon);
          const color = isTransfer || isSplit ? "var(--text-muted)" : tx.category?.color ?? "var(--text-muted)";
          const categoryLabel = isSplit
            ? tx.splits.map((split) => (split.category ? translateCategoryName(split.category.name) : "?")).join(" + ")
            : tx.category
              ? categoryPath(tx.category, categories)
              : null;

          return (
            <li key={tx.id} className="group flex items-center gap-3 py-3">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                style={{ backgroundColor: typeof color === "string" && color.startsWith("#") ? `${color}26` : "var(--surface-2)" }}
              >
                <Icon size={16} style={{ color }} />
              </span>

              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-text-primary">{tx.description}</span>
                <span className="block truncate text-xs text-text-muted">
                  {formatTransactionDate(tx.date, Boolean(onJumpToMonth))} · {tx.account.name}
                  {isTransfer && tx.transfer_account_id ? ` ${t("transactions.transferSuffix")}` : ""}
                  {categoryLabel ? ` · ${categoryLabel}` : ""}
                  {tx.tags.length > 0 ? ` · ${tx.tags.map((tag) => tag.name).join(", ")}` : ""}
                </span>
              </span>

              {/* Знак и цвет берутся из общего модуля, а не решаются здесь.
                  Раньше решались: всё, что не перевод и не расход, шло
                  зелёным плюсом, и переданный человеку подарок выглядел
                  как заработок. */}
              <span
                className={`shrink-0 text-sm font-medium tabular-nums ${amountColorClass(tx.type)}`}
              >
                {amountSign(tx.type)}
                {formatCurrency(tx.amount, tx.currency)}
                {/* Вторым числом — сколько это в валюте установки, по курсу
                    дня операции. Только у валютной операции. */}
                {tx.currency !== base && (
                  <span className="block text-xs font-normal text-text-muted">
                    {tx.amount_base === null
                      ? t("transactions.rateMissing")
                      : formatCurrency(tx.amount_base, base)}
                  </span>
                )}
              </span>

              <span className="flex shrink-0 gap-1">
                {onJumpToMonth && (
                  <button
                    type="button"
                    aria-label={t("transactions.jumpToMonth")}
                    onClick={() => onJumpToMonth(tx)}
                    className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                  >
                    <CalendarSearch size={15} />
                  </button>
                )}
                <button
                  type="button"
                  aria-label={t("common.edit")}
                  onClick={() => onEdit(tx)}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                >
                  <Pencil size={15} />
                </button>
                <button
                  type="button"
                  aria-label={t("common.delete")}
                  onClick={() => onDelete(tx)}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                >
                  <Trash2 size={15} />
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </>
  );
}
