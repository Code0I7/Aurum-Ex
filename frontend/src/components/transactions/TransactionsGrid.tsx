import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, ChevronDown, ChevronRight, GripVertical, Pencil, SquareDivide, Trash2 } from "lucide-react";
import { useCategories } from "@/hooks/useCategories";
import { useCounterparties, useParticipants, useStores } from "@/hooks/useDirectories";
import { categoryPath, translateCategoryName } from "@/lib/categoryLabels";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency, formatDayHeading, formatTransactionDate } from "@/lib/format";
import { formatWorkCost, rateForDate } from "@/lib/hours";
import { useHourlyRates } from "@/hooks/usePlans";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { amountColorClass, amountSign } from "@/lib/transactionAmount";
import { COLUMNS, type ColumnId, type ColumnLayout } from "@/components/transactions/columns";
import { groupTransactions } from "@/components/transactions/grouping";
import { useRowDrag, type DragUnit, type RowMeta } from "@/components/transactions/useRowDrag";
import type { Transaction } from "@/types";

interface TransactionsGridProps {
  items: Transaction[];
  layout: ColumnLayout;
  onEdit: (transaction: Transaction) => void;
  onDelete: (transaction: Transaction) => void;
  /** Перестановка строки внутри её дня по визуальной позиции. Между днями
   * строка не переносится: дату меняют редактированием даты, а не
   * движением мыши. */
  /** Переставить операции внутри дня: идентификаторы в порядке дня и
   *  место, на которое встаёт весь блок. */
  onReorder: (ids: number[], position: number) => void;
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
  const { t, currency: base } = useTranslation();
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
  const tableRef = useRef<HTMLTableElement>(null);
  const groups = useMemo(() => groupTransactions(items, groupRepeats), [items, groupRepeats]);

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

  // Соседи по дню — то, внутри чего разрешено перетаскивание. Счёт роли не
  // играет: в списке счета идут вперемешку, и порядок дня сквозной.
  // Считается один раз на весь список: искать их заново на каждое движение
  // мыши было бы расточительно.
  //
  // Единица перетаскивания — видимая строка, а не запись: свёрнутая группа
  // это одна строка и несколько записей, и двигается она целиком.
  // Раскрытая группа единицей не считается — там видны сами операции, и
  // тянут именно их.
  const siblingsByRow = useMemo(() => {
    const byDay = new Map<string, RowMeta[]>();
    for (const group of groups) {
      const asOneRow = group.items.length > 1 && !expanded.has(group.key);
      const units: DragUnit[] = asOneRow
        ? [{ key: group.key, items: group.items }]
        : group.items.map((tx) => ({ key: String(tx.id), items: [tx] }));
      for (const unit of units) {
        const dayKey = unit.items[0].date;
        const list = byDay.get(dayKey) ?? [];
        list.push({ unit, indexInDay: list.length });
        byDay.set(dayKey, list);
      }
    }
    // День запоминается у каждой строки. Номер строки внутри дня сам по
    // себе ничего не опознаёт: третья строка есть в каждом дне, и подсветка
    // места вставки по одному номеру загоралась разом во всём списке.
    const result = new Map<string, { dayKey: string; meta: RowMeta; siblings: RowMeta[] }>();
    for (const [dayKey, list] of byDay) {
      for (const meta of list) result.set(meta.unit.key, { dayKey, meta, siblings: list });
    }
    return result;
  }, [groups, expanded]);

  // Куда встанет перетаскиваемая строка, в порядке дня.
  //
  // Список показан от новых операций к старым, а хранится наоборот, поэтому
  // позиция блока — это число операций, оказавшихся визуально НИЖЕ него.
  const handleDrop = useCallback(
    (row: RowMeta, targetIndex: number, siblings: RowMeta[]) => {
      const rest = siblings.filter((item) => item.unit.key !== row.unit.key);
      const at = Math.max(0, Math.min(targetIndex, rest.length));
      const below = rest.slice(at).reduce((sum, item) => sum + item.unit.items.length, 0);
      // Внутри блока порядок сохраняется, но серверу он нужен в порядке
      // дня — от старой операции к новой, — а показан обратный.
      onReorder([...row.unit.items].reverse().map((tx) => tx.id), below);
    },
    [onReorder]
  );

  const { drag, arm, move, end, consumeClickSuppression } = useRowDrag(handleDrop);

  // Прокрутка таблицы вбок и её ползунок внизу экрана — два элемента,
  // показывающих одно и то же положение, поэтому их приходится держать в
  // согласии вручную.
  //
  // Эхо гасится сравнением с последним записанным значением, а не флагом на
  // время обработчика. Флаг не работал: браузер сообщает о прокрутке
  // асинхронно, к тому моменту флаг уже снят, и на телефоне выходило вот
  // что. Палец бросает таблицу с разгона, мы двигаем ползунок, ползунок
  // сообщает о своей прокрутке — и мы возвращаем таблицу туда, где она была
  // в начале кадра, обрывая инерцию. Медленное движение инерции не даёт,
  // поэтому и работало.
  const scrollRef = useRef<HTMLDivElement>(null);
  const railRef = useRef<HTMLDivElement>(null);
  const written = useRef({ table: -1, rail: -1 });
  const [tableWidth, setTableWidth] = useState(0);
  const [overflows, setOverflows] = useState(false);

  useEffect(() => {
    const table = tableRef.current;
    const box = scrollRef.current;
    if (!table || !box) return;
    // Ширина считается наблюдателем, а не при отрисовке: она меняется от
    // набора колонок, от длины описаний и от размера окна, и каждый из этих
    // случаев иначе пришлось бы ловить отдельно.
    const observer = new ResizeObserver(() => {
      setTableWidth(table.scrollWidth);
      setOverflows(table.scrollWidth > box.clientWidth + 1);
    });
    observer.observe(table);
    observer.observe(box);
    return () => observer.disconnect();
  }, [columns.length, items.length]);

  const syncFromTable = () => {
    const box = scrollRef.current;
    const rail = railRef.current;
    if (!box || !rail) return;
    // Это наше же эхо от записи в таблицу — отвечать на него нечем.
    if (Math.abs(box.scrollLeft - written.current.table) < 1) {
      written.current.table = -1;
      return;
    }
    written.current.rail = box.scrollLeft;
    rail.scrollLeft = box.scrollLeft;
  };

  const syncFromRail = () => {
    const box = scrollRef.current;
    const rail = railRef.current;
    if (!box || !rail) return;
    if (Math.abs(rail.scrollLeft - written.current.rail) < 1) {
      written.current.rail = -1;
      return;
    }
    written.current.table = rail.scrollLeft;
    box.scrollLeft = rail.scrollLeft;
  };

  // День перетаскиваемой строки: только внутри него разрешено
  // переставлять, и только там показывается место вставки.
  const dragDayKey = drag ? siblingsByRow.get(drag.key)?.dayKey : undefined;

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
        // Значок берётся у выбранной категории, а не у корня ветки: у
        // «Продукты · Молочное · Сыр» родительские значки ничего не
        // добавляют, а колонка от трёх иконок подряд превращается в
        // мельтешение. Значок один и стоит перед путём.
        if (tx.splits.length > 0) {
          // У разбивки значка нет: категорий несколько, и любая
          // выбранная означала бы, что остальные менее важны.
          return tx.splits
            .map((split) => (split.category ? translateCategoryName(split.category.name) : "?"))
            .join(" + ");
        }
        if (!tx.category) return "—";
        const CategoryIcon = getCategoryIcon(tx.category.icon);
        return (
          <span className="flex items-center gap-1.5">
            <CategoryIcon
              size={13}
              className="shrink-0"
              style={{ color: tx.category.color }}
              aria-hidden
            />
            <span className="truncate">{categoryPath(tx.category, categories)}</span>
          </span>
        );
      }

      case "account":
        return tx.account.name;

      case "amount": {
        // Знак и цвет — из общего модуля: раньше эта развилка жила
        // в каждом списке своя, и списки разошлись.
        const sign = amountSign(tx.type);
        // У свёрнутой группы показывается сумма по всем её операциям: четыре
        // поездки по 35 ₽ читаются как 140 ₽, иначе группировка скрывала бы
        // ровно то число, ради которого в список и смотрят.
        const amount = group ? group.total : tx.amount;
        // Расход красным, приход зелёным. Раньше цвет был только у прихода,
        // а расход шёл тем же приглушённым серым, что и остальной текст
        // строки: на сером фоне число терялось ровно там, где список и
        // читают — глазами по колонке сумм.
        //
        // Перевод остаётся серым намеренно: свои деньги переложены с одного
        // счёта на другой, ни потери, ни прибавления не произошло, и красный
        // говорил бы неправду.
        return (
          <span
            className={cn(
              "tabular-nums",
              tx.is_excluded && "line-through opacity-60",
              // Перевод без своего цвета: строка сетки уже окрашена,
              // и серый у одной колонки выбивался бы из ряда.
              amountColorClass(tx.type, "")
            )}
          >
            {sign}
            {formatCurrency(amount, tx.currency)}
            {/* Вторым числом — сколько это в валюте установки, по курсу дня
                операции. Только у валютной: у своей это было бы одно и то же
                число дважды. Одного первого мало — его не с чем сравнить в
                списке; одного второго мало — оно врёт про ценник. */}
            {tx.currency !== base && (
              <span className="block text-xs font-normal text-text-muted">
                {tx.amount_base === null
                  ? t("transactions.rateMissing")
                  : formatCurrency(tx.amount_base, base)}
              </span>
            )}
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
    <div className="relative">
      <div ref={scrollRef} className="overflow-x-auto" onScroll={syncFromTable}>
      <table ref={tableRef} className="w-full min-w-max border-collapse text-sm">
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
                      {/* Итог дня теми же цветами, что и суммы в строках:
                          потрачено красным, получено зелёным. Серым он
                          сливался с датой рядом, хотя это и есть главное
                          число разделителя. */}
                      {totals && totals.spent > 0 && (
                        <span className="text-xs tabular-nums text-danger">
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
                  data-row-key={groupRow.key}
                  // Свёрнутая группа тянется как одна строка — целиком.
                  // «Автобус ×4» на экране одна строка, а в базе четыре
                  // записи, и двигать их по очереди нельзя: после первой же
                  // перестановки нумерация меняется, и остальные уезжают не
                  // туда.
                  onPointerDown={(event) => {
                    if ((event.target as HTMLElement).closest("button, a, input")) return;
                    const found = siblingsByRow.get(groupRow.key);
                    if (!found) return;
                    arm(event, found.meta, found.siblings);
                  }}
                  onPointerMove={move}
                  onPointerUp={end}
                  // Свёрнутая группа подсвечена акцентом и линией слева —
                  // той же, что помечает её раскрытые строки, чтобы связь
                  // между шапкой и содержимым читалась без раскрытия.
                  className={cn(
                    "group cursor-pointer bg-accent/[0.06] hover:bg-accent/10",
                    drag?.key === groupRow.key && "opacity-40",
                    drag &&
                      drag.key !== groupRow.key &&
                      siblingsByRow.get(groupRow.key)?.dayKey === dragDayKey &&
                      drag.targetIndex === siblingsByRow.get(groupRow.key)?.meta.indexInDay &&
                      "border-t-[3px] border-accent bg-accent/10 shadow-[0_-2px_10px_-2px_var(--color-accent)]"
                  )}
                  onClick={() => {
                    // Щелчок после перетаскивания — не щелчок: человек
                    // двигал группу, а не раскрывал её.
                    if (consumeClickSuppression()) return;
                    toggleGroup(groupRow.key);
                  }}
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
                          {/* Ручка перетаскивания группы. Как у обычной
                              строки: пальцем за тело тянуть нельзя, свайп
                              прокрутки неотличим от начала жеста. */}
                          {(siblingsByRow.get(groupRow.key)?.siblings.length ?? 0) > 1 && (
                            <button
                              type="button"
                              aria-label={t("transactions.dragHandle")}
                              title={t("transactions.dragHandle")}
                              onPointerDown={(event) => {
                                event.stopPropagation();
                                const found = siblingsByRow.get(groupRow.key);
                                if (!found) return;
                                arm(event, found.meta, found.siblings, true);
                              }}
                              onPointerMove={move}
                              onPointerUp={end}
                              onClick={(event) => event.stopPropagation()}
                              className="-ml-1 cursor-grab touch-none rounded p-0.5 text-text-muted transition active:cursor-grabbing sm:hidden"
                            >
                              <GripVertical size={13} />
                            </button>
                          )}
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
              data-row-key={String(tx.id)}
              // Тянуть можно за само тело строки: перетаскивание начнётся,
              // только когда указатель уйдёт с места. Кнопки внутри строки
              // исключены — иначе нажатие на «удалить» превращалось бы в
              // перетаскивание.
              onPointerDown={(event) => {
                if ((event.target as HTMLElement).closest("button, a, input")) return;
                const found = siblingsByRow.get(String(tx.id));
                if (!found) return;
                arm(event, found.meta, found.siblings);
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
                drag?.key === String(tx.id) && "opacity-40",
                drag &&
                  drag.key !== String(tx.id) &&
                  // Тот же день, а не просто тот же номер строки: без этой
                  // проверки загоралась третья строка каждого дня сразу.
                  siblingsByRow.get(String(tx.id))?.dayKey === dragDayKey &&
                  drag.targetIndex === siblingsByRow.get(String(tx.id))?.meta.indexInDay &&
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
                      {(siblingsByRow.get(String(tx.id))?.siblings.length ?? 0) > 1 && (
                      <button
                        type="button"
                        aria-label={t("transactions.dragHandle")}
                        title={t("transactions.dragHandle")}
                        onPointerDown={(event) => {
                          const found = siblingsByRow.get(String(tx.id));
                          if (!found) return;
                          arm(event, found.meta, found.siblings, true);
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

      {/* Ползунок, прилипший к нижнему краю экрана.
          Прокрутка у таблицы была и раньше, но её полоса — у нижнего края
          самой таблицы, а таблица длиной в месяц операций уходит далеко за
          экран. Чтобы добраться до полосы, приходилось прокручивать
          страницу до конца списка; вместо этого люди тянули страницу вбок,
          и вкладки с кнопками уезжали за край.

          Снизу, а не сверху: сверху уже висит шапка приложения, и два
          прилипших элемента спорили бы за место. Появляется только когда
          таблица действительно шире экрана — полоса прокрутки под тем, что
          и так помещается, лишь занимает место. */}
      {overflows && (
        <div
          ref={railRef}
          onScroll={syncFromRail}
          className="sticky bottom-0 z-10 overflow-x-auto rounded-b-xl border-t border-gridline bg-surface-1/95 backdrop-blur"
          aria-hidden
        >
          <div style={{ width: tableWidth }} className="h-2.5" />
        </div>
      )}
    </div>
  );
}
