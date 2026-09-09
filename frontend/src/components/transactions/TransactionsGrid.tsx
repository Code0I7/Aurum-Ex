import { useMemo, useState } from "react";
import { ArrowLeftRight, ChevronDown, ChevronRight, GripVertical, Pencil, SquareDivide, Trash2 } from "lucide-react";
import { useCategories } from "@/hooks/useCategories";
import { useCounterparties, useParticipants, useStores } from "@/hooks/useDirectories";
import { categoryPath, translateCategoryName } from "@/lib/categoryLabels";
import { formatCurrency, formatDayHeading, formatTransactionDate } from "@/lib/format";
import { formatWorkCost, rateForDate } from "@/lib/hours";
import { useHourlyRates } from "@/hooks/usePlans";
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
  /** Показывать ли заголовки дней с итогами. Кому-то нужен сплошной
   * список без лишних строк. */
  dayDividers: boolean;
  /**
   * Идёт ли список по датам.
   *
   * Разделители дней имеют смысл только тогда. При сортировке по сумме даты
   * идут вперемешку, и правило «дата отличается от предыдущей строки» ставит
   * плашку почти над каждой строкой, а один и тот же день получает её
   * столько раз, сколько раз прерывается.
   */
  chronological: boolean;
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
export function TransactionsGrid({
  items,
  layout,
  onEdit,
  onDelete,
  onReorder,
  groupRepeats,
  dayDividers,
  chronological,
}: TransactionsGridProps) {
  const { t } = useTranslation();
  const { data: categories } = useCategories();
  const { data: rates } = useHourlyRates();
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
  const { drag, arm, move, end, consumeClickSuppression } = useRowDrag(onReorder);

  // Итог по каждому дню — то, что в банковских выписках стоит в шапке дня.
  // Переводы в него не входят: это движение своих же денег между
  // собственными счетами, и в трату оно превращается только на бумаге.
  const dayTotals = useMemo(() => {
    const totals = new Map<string, { spent: number; earned: number }>();
    for (const tx of items) {
      if (tx.is_excluded || tx.type === "transfer") continue;
      const current = totals.get(tx.date) ?? { spent: 0, earned: 0 };
      if (tx.type === "income" || tx.type === "external_in") current.earned += Number(tx.amount);
      else current.spent += Number(tx.amount);
      totals.set(tx.date, current);
    }
    return totals;
  }, [items]);

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
        return <span className="tabular-nums text-text-muted">{formatTransactionDate(tx.date)}</span>;

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

      case "workCost": {
        // Цена в рублях привычна и потому почти не ощущается; цена в рабочих
        // днях ощущается сразу. Ставка берётся за месяц операции: за четыре
        // года заработок меняется втрое.
        const amount = group ? group.total : tx.amount;
        const cost = formatWorkCost(amount, rateForDate(rates, tx.date));
        return cost === null ? (
          <span className="text-text-muted">—</span>
        ) : (
          <span className="tabular-nums text-text-muted">{cost}</span>
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
          {groups.flatMap((groupRow, groupIndex) => {
            const collapsed = groupRow.items.length > 1;
            // Разделитель дня — как в банковском приложении: дата и итог
            // за день над блоком его операций. Ставится при смене даты, а
            // не перед каждой строкой.
            const previousDate = groupIndex > 0 ? groups[groupIndex - 1].head.date : null;
            const startsNewDay = dayDividers && chronological && groupRow.head.date !== previousDate;
            const totals = dayTotals.get(groupRow.head.date);
            const isOpen = expanded.has(groupRow.key);
            // Свёрнутая группа рисуется как одна строка; раскрытая — как
            // заголовок плюс её собственные операции, каждая со своим
            // балансом и своими действиями.
            const rows = collapsed && !isOpen ? [] : groupRow.items;

            return [
              startsNewDay ? (
                <tr key={`day-${groupIndex}-${groupRow.head.date}`} className="bg-surface-2/30">
                  <td colSpan={columns.length + 1} className="px-3 py-1.5">
                    <span className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                      <span className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                        {formatDayHeading(groupRow.head.date)}
                      </span>
                      {totals && totals.spent > 0 && (
                        <span className="text-xs tabular-nums text-text-muted">
                          −{formatCurrency(totals.spent, groupRow.head.currency)}
                        </span>
                      )}
                      {totals && totals.earned > 0 && (
                        <span className="text-xs tabular-nums text-success">
                          +{formatCurrency(totals.earned, groupRow.head.currency)}
                        </span>
                      )}
                    </span>
                  </td>
                </tr>
              ) : null,
              collapsed ? (
                <tr
                  key={groupRow.key}
                  // Свёрнутая группа подсвечена акцентом и линией слева —
                  // той же, что помечает её раскрытые строки, чтобы связь
                  // между шапкой и содержимым читалась без раскрытия.
                  className="group cursor-pointer bg-accent/[0.06] hover:bg-accent/10"
                  onClick={() => toggleGroup(groupRow.key)}
                >
                  {columns.map((column, index) => (
                    <td
                      key={column.id}
                      className={cn(
                        "max-w-[280px] truncate px-3 py-2 text-text-primary",
                        column.align === "right" && "text-right",
                        index === 0 && "border-l-2 border-accent/40"
                      )}
                    >
                      {/* Флексом оборачивается только первая колонка — та,
                          где стоит стрелка. Раньше в него попадали все, и
                          text-right переставал действовать: у флекс-строки
                          выравнивание задаёт justify-content, а не
                          text-align. Из-за этого «Сумма» и «Баланс после» у
                          свёрнутой группы уезжали влево, хотя внутри
                          раскрытой группы стояли ровно. */}
                      {index === 0 ? (
                        <span className="flex items-center gap-1">
                          {isOpen ? (
                            <ChevronDown size={13} className="shrink-0 text-accent/70" />
                          ) : (
                            <ChevronRight size={13} className="shrink-0 text-accent/70" />
                          )}
                          {renderCell(column.id, groupRow.head, {
                            count: groupRow.items.length,
                            total: groupRow.total,
                          })}
                        </span>
                      ) : (
                        renderCell(column.id, groupRow.head, {
                          count: groupRow.items.length,
                          total: groupRow.total,
                        })
                      )}
                    </td>
                  ))}
                  <td className="px-3 py-2" />
                </tr>
              ) : null,
              ...rows.map((tx) => (
            <tr
              key={tx.id}
              data-row-id={tx.id}
              // Тянуть можно за само тело строки: перетаскивание начнётся,
              // только когда указатель уйдёт с места. Кнопки внутри строки
              // исключены — иначе нажатие на «удалить» превращалось бы в
              // перетаскивание.
              onPointerDown={(event) => {
                if ((event.target as HTMLElement).closest("button, a, input")) return;
                const meta = siblingsByRow.get(tx.id);
                if (!meta) return;
                arm(event, { transaction: tx, indexInDay: meta.indexInDay }, meta.siblings);
              }}
              onPointerMove={move}
              onPointerUp={end}
              // Щелчок по строке открывает правку. Кнопка карандаша
              // осталась: она объясняет, что строка вообще нажимается, —
              // без неё об этом можно не догадаться.
              onClick={(event) => {
                // Клик по кнопке внутри строки — это её собственное
                // действие: удаление, перетаскивание, разбор чека. Проверка
                // по ближайшей кнопке, а не по списку — иначе следующая
                // добавленная кнопка молча начала бы открывать редактор.
                if ((event.target as HTMLElement).closest("button, a, input")) return;
                // Щелчок после перетаскивания — не щелчок: человек двигал
                // строку, а не открывал её.
                if (consumeClickSuppression()) return;
                // Выделение текста мышью заканчивается щелчком по строке.
                // Открывать редактор в ответ на попытку скопировать сумму
                // значит отменять эту попытку.
                if (window.getSelection()?.toString()) return;
                onEdit(tx);
              }}
              className={cn(
                "group cursor-pointer transition-colors hover:bg-surface-2/40",
                collapsed && "bg-surface-2/20",
                // Перетаскиваемая строка бледнеет, а место, куда она встанет,
                // подсвечивается линией сверху — так видно результат до того,
                // как отпустишь.
                //
                // Линия в два пикселя цветом рамки терялась среди самих
                // разделителей строк: на телефоне разглядеть, куда именно
                // встанет операция, было нельзя. Поэтому три пикселя,
                // акцентный цвет в полную силу, свечение вокруг и
                // подкрашенный фон самой строки — цель должна читаться
                // боковым зрением, не глазами.
                drag?.id === tx.id && "opacity-40",
                drag && drag.id !== tx.id && drag.targetIndex === siblingsByRow.get(tx.id)?.indexInDay &&
                  "border-t-[3px] border-accent bg-accent/10 shadow-[0_-2px_10px_-2px_var(--color-accent)]"
              )}
            >
              {columns.map((column, columnIndex) => (
                <td
                  key={column.id}
                  className={cn(
                    "max-w-[280px] truncate px-3 py-2 text-text-primary",
                    column.align === "right" && "text-right",
                    // Принадлежность к группе показывается фоном строки и
                    // тонкой линией у левого края, а не отступом: любой
                    // отступ сдвигает содержимое, и колонки раскрытой группы
                    // перестают совпадать с колонками таблицы.
                    collapsed && columnIndex === 0 && "border-l-2 border-accent/25"
                  )}
                >
                  {columnIndex === 0 ? (
                    <span className="flex items-center gap-1.5">
                      {/* Ручка перетаскивания. touch-action: none — иначе
                          палец, ведущий строку вверх, вместо этого
                          прокручивает страницу. */}
                      {/* Ручка появляется, только когда есть что переставлять.
                          Единственная операция дня никуда не двигается, и
                          ручка над ней — обещание, которого приложение не
                          выполняет: нажал, потянул, ничего не произошло. */}
                      {(siblingsByRow.get(tx.id)?.siblings.length ?? 0) > 1 && (
                      <button
                        type="button"
                        aria-label={t("transactions.dragHandle")}
                        title={t("transactions.dragHandle")}
                        onPointerDown={(event) => {
                          const meta = siblingsByRow.get(tx.id);
                          if (!meta) return;
                          arm(event, { transaction: tx, indexInDay: meta.indexInDay }, meta.siblings, true);
                        }}
                        // Только на узких экранах. Пальцем за тело строки
                        // тянуть нельзя: браузер решает «прокрутка или жест»
                        // в момент касания, и отдать движение нам можно
                        // только выключив прокрутку заранее — то есть для
                        // всего списка. Ручка — единственное место, где
                        // touch-action выключен, поэтому список
                        // прокручивается как обычно.
                        className="-ml-1 cursor-grab touch-none rounded p-0.5 text-text-muted transition active:cursor-grabbing sm:hidden"
                      >
                        <GripVertical size={13} />
                      </button>
                      )}
                      {renderCell(column.id, tx)}
                    </span>
                  ) : (
                    renderCell(column.id, tx)
                  )}
                </td>
              ))}
              <td className="whitespace-nowrap px-3 py-2 text-right">
                {/* На узком экране кнопки видны всегда. Прятать их до наведения
                      значило прятать навсегда: на телефоне наведения не
                      существует, и до правки с удалением было не добраться
                      вообще. */}
                <span className="inline-flex items-center gap-0.5 transition sm:opacity-0 sm:transition sm:group-hover:opacity-100 sm:focus-within:opacity-100">
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
