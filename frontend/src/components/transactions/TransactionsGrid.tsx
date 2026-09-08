import { useMemo, useState } from "react";
import { ArrowLeftRight, ChevronDown, ChevronRight, GripVertical, Pencil, SquareDivide, Trash2 } from "lucide-react";
import { useCategories } from "@/hooks/useCategories";
import { useCounterparties, useParticipants, useStores } from "@/hooks/useDirectories";
import { categoryPath, translateCategoryName } from "@/lib/categoryLabels";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { COLUMNS, type ColumnId, type ColumnLayout } from "@/components/transactions/columns";
import { groupTransactions } from "@/components/transactions/grouping";
import { useRowDrag } from "@/components/transactions/useRowDrag";
import type { Transaction } from "@/types";

interface TransactionsGridProps {
  items: Transaction[];
  layout: ColumnLayout;
  onEdit: (transaction: Transaction) => void;
  onDelete: (transaction: Transaction) => void;
  /** Перестановка строки внутри её дня по визуальной позиции. Между днями
   * строка не переносится: дату меняют редактированием даты, а не
   * движением мыши. */
  onReorder: (transaction: Transaction, visualIndex: number, countInDay: number) => void;
  /** Склеивать ли одинаковые операции одного дня в одну строку — четыре
   * поездки на автобусе показываются как «Автобус ×4». */
  groupRepeats: boolean;
}

/**
 * Табличный вид списка операций — то, ради чего человек и просил уйти от
 * карточек: видеть много строк сразу, скрывать лишние колонки и следить за
 * балансом счёта по ходу.
 *
 * Мобильная адаптация не в том, чтобы ужать таблицу: на узком экране она
 * прокручивается вбок вместе с шапкой, а первые две колонки — дата и
 * описание — остаются на месте, иначе при прокрутке непонятно, чья это
 * строка.
 *
 * Порядок внутри дня меняется кнопками, а не перетаскиванием: на телефоне
 * перетаскивание конфликтует с прокруткой страницы, а кнопки одинаково
 * работают и мышью, и пальцем, и с клавиатуры.
 */
export function TransactionsGrid({ items, layout, onEdit, onDelete, onReorder, groupRepeats }: TransactionsGridProps) {
  const { t } = useTranslation();
  const { data: categories } = useCategories();
  const { data: participants } = useParticipants();
  const { data: stores } = useStores();
  const { data: counterparties } = useCounterparties();

  const columns = useMemo(
    () =>
      layout.visible
        .map((id) => COLUMNS.find((column) => column.id === id))
        .filter((column): column is (typeof COLUMNS)[number] => Boolean(column)),
    [layout.visible]
  );

  // Какие группы раскрыты. По ключу группы, а не по индексу: список
  // перерисовывается после каждой правки, и индекс раскрыл бы соседа.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const groups = useMemo(() => groupTransactions(items, groupRepeats), [items, groupRepeats]);
  const { drag, start, move, end } = useRowDrag(onReorder);

  // Соседи по дню и счёту — то, внутри чего разрешено перетаскивание.
  // Считается один раз на весь список: искать их заново на каждое движение
  // мыши было бы расточительно.
  const siblingsByRow = useMemo(() => {
    const byDay = new Map<string, Transaction[]>();
    for (const tx of items) {
      const key = `${tx.date}|${tx.account_id}`;
      byDay.set(key, [...(byDay.get(key) ?? []), tx]);
    }
    const result = new Map<number, { indexInDay: number; siblings: { transaction: Transaction; indexInDay: number }[] }>();
    for (const rows of byDay.values()) {
      const meta = rows.map((transaction, indexInDay) => ({ transaction, indexInDay }));
      meta.forEach((item) => result.set(item.transaction.id, { indexInDay: item.indexInDay, siblings: meta }));
    }
    return result;
  }, [items]);

  const toggleGroup = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const nameById = useMemo(
    () => ({
      participant: new Map((participants ?? []).map((row) => [row.id, row.name])),
      store: new Map((stores ?? []).map((row) => [row.id, row.name])),
      counterparty: new Map((counterparties ?? []).map((row) => [row.id, row.name])),
    }),
    [participants, stores, counterparties]
  );

  if (items.length === 0) {
    return <p className="py-12 text-center text-sm text-text-muted">{t("transactions.noneFound")}</p>;
  }

  const renderCell = (column: ColumnId, tx: Transaction, group?: { count: number; total: number }) => {
    switch (column) {
      case "date":
        return <span className="tabular-nums">{formatTransactionDate(tx.date)}</span>;

      case "description":
        return (
          <span className="flex items-center gap-1.5">
            {tx.type === "transfer" && <ArrowLeftRight size={13} className="shrink-0 text-text-muted" />}
            {tx.splits.length > 0 && <SquareDivide size={13} className="shrink-0 text-text-muted" />}
            <span className={cn("truncate", tx.is_excluded && "line-through opacity-60")}>{tx.description}</span>
            {group && (
              <span className="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 text-xs tabular-nums text-text-muted">
                ×{group.count}
              </span>
            )}
          </span>
        );

      case "category": {
        if (tx.splits.length > 0) {
          return tx.splits
            .map((split) => (split.category ? translateCategoryName(split.category.name) : "?"))
            .join(" + ");
        }
        return tx.category ? categoryPath(tx.category, categories) : "—";
      }

      case "account":
        return tx.account.name;

      case "amount": {
        const sign = tx.type === "income" || tx.type === "external_in" ? "+" : tx.type === "transfer" ? "" : "−";
        // У свёрнутой группы показывается сумма по всем её операциям: четыре
        // поездки по 35 ₽ читаются как 140 ₽, иначе группировка скрывала бы
        // ровно то число, ради которого в список и смотрят.
        const amount = group ? group.total : tx.amount;
        return (
          <span
            className={cn(
              "tabular-nums",
              tx.is_excluded && "line-through opacity-60",
              tx.type === "income" && "text-success"
            )}
          >
            {sign}
            {formatCurrency(amount, tx.currency)}
          </span>
        );
      }

      case "balance":
        // Баланс приходит только в списке; в ответе на правку его нет.
        return tx.balance_after === null ? (
          "—"
        ) : (
          <span className={cn("tabular-nums", Number(tx.balance_after) < 0 && "text-danger")}>
            {formatCurrency(tx.balance_after, tx.account.currency)}
          </span>
        );

      case "participant":
        return tx.participant_id ? (nameById.participant.get(tx.participant_id) ?? "—") : "—";
      case "store":
        return tx.store_id ? (nameById.store.get(tx.store_id) ?? "—") : "—";
      case "counterparty":
        return tx.counterparty_id ? (nameById.counterparty.get(tx.counterparty_id) ?? "—") : "—";

      case "tags":
        return tx.tags.length ? tx.tags.map((tag) => tag.name).join(", ") : "—";
      case "note":
        return tx.notes ?? "—";
      case "currency":
        return tx.currency;
      case "uuid":
        return <span className="font-mono text-[11px] text-text-muted">{tx.uuid}</span>;

      default:
        return "—";
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-max border-collapse text-sm">
        <thead>
          <tr className="border-b border-gridline text-left">
            {columns.map((column) => (
              <th
                key={column.id}
                scope="col"
                style={{ minWidth: column.width }}
                className={cn(
                  "px-3 py-2 text-xs font-medium uppercase tracking-wide text-text-muted",
                  column.align === "right" && "text-right"
                )}
              >
                {t(column.labelKey)}
              </th>
            ))}
            <th scope="col" className="px-3 py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gridline">
          {groups.flatMap((groupRow) => {
            const collapsed = groupRow.items.length > 1;
            const isOpen = expanded.has(groupRow.key);
            // Свёрнутая группа рисуется как одна строка; раскрытая — как
            // заголовок плюс её собственные операции, каждая со своим
            // балансом и своими действиями.
            const rows = collapsed && !isOpen ? [] : groupRow.items;

            return [
              collapsed ? (
                <tr
                  key={groupRow.key}
                  className="group cursor-pointer hover:bg-surface-2/40"
                  onClick={() => toggleGroup(groupRow.key)}
                >
                  {columns.map((column, index) => (
                    <td
                      key={column.id}
                      className={cn(
                        "max-w-[280px] truncate px-3 py-2 text-text-primary",
                        column.align === "right" && "text-right"
                      )}
                    >
                      <span className="flex items-center gap-1">
                        {index === 0 &&
                          (isOpen ? (
                            <ChevronDown size={13} className="shrink-0 text-text-muted" />
                          ) : (
                            <ChevronRight size={13} className="shrink-0 text-text-muted" />
                          ))}
                        {renderCell(column.id, groupRow.head, {
                          count: groupRow.items.length,
                          total: groupRow.total,
                        })}
                      </span>
                    </td>
                  ))}
                  <td className="px-3 py-2" />
                </tr>
              ) : null,
              ...rows.map((tx) => (
            <tr
              key={tx.id}
              data-row-id={tx.id}
              onPointerMove={move}
              onPointerUp={end}
              className={cn(
                "group transition-colors hover:bg-surface-2/40",
                collapsed && "bg-surface-2/20",
                // Перетаскиваемая строка бледнеет, а место, куда она встанет,
                // подсвечивается линией сверху — так видно результат до того,
                // как отпустишь.
                drag?.id === tx.id && "opacity-40",
                drag && drag.id !== tx.id && drag.targetIndex === siblingsByRow.get(tx.id)?.indexInDay &&
                  "border-t-2 border-accent"
              )}
            >
              {columns.map((column, columnIndex) => (
                <td
                  key={column.id}
                  className={cn(
                    "max-w-[280px] truncate px-3 py-2 text-text-primary",
                    column.align === "right" && "text-right",
                    // Операции раскрытой группы сдвинуты вправо, чтобы было
                    // видно, что они относятся к строке выше.
                    collapsed && "pl-7"
                  )}
                >
                  {columnIndex === 0 ? (
                    <span className="flex items-center gap-1.5">
                      {/* Ручка перетаскивания. touch-action: none — иначе
                          палец, ведущий строку вверх, вместо этого
                          прокручивает страницу. */}
                      <button
                        type="button"
                        aria-label={t("transactions.dragHandle")}
                        title={t("transactions.dragHandle")}
                        onPointerDown={(event) => {
                          const meta = siblingsByRow.get(tx.id);
                          if (!meta || meta.siblings.length < 2) return;
                          start(event, { transaction: tx, indexInDay: meta.indexInDay }, meta.siblings);
                        }}
                        className="-ml-1 cursor-grab touch-none rounded p-0.5 text-text-muted opacity-0 transition group-hover:opacity-100 active:cursor-grabbing"
                      >
                        <GripVertical size={13} />
                      </button>
                      {renderCell(column.id, tx)}
                    </span>
                  ) : (
                    renderCell(column.id, tx)
                  )}
                </td>
              ))}
              <td className="whitespace-nowrap px-3 py-2 text-right">
                <span className="inline-flex items-center gap-0.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                  <button
                    type="button"
                    onClick={() => onEdit(tx)}
                    title={t("common.edit")}
                    className="rounded p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(tx)}
                    title={t("common.delete")}
                    className="rounded p-1 text-text-muted hover:bg-surface-2 hover:text-danger"
                  >
                    <Trash2 size={14} />
                  </button>
                </span>
              </td>
            </tr>
              )),
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}
