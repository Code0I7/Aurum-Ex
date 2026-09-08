import type { TranslationKey } from "@/lib/i18n";
import type { Transaction } from "@/types";

/**
 * Описание колонок таблицы транзакций: что показывать, в каком порядке и
 * какие из них видны.
 *
 * Вынесено в данные, а не зашито в разметку, ровно по той причине, по
 * которой человек просил табличный вид: колонки надо уметь прятать и
 * переставлять. Из разметки такое не достаётся — пришлось бы писать
 * отдельную ветку под каждое сочетание.
 *
 * Набор по умолчанию собран из того, что в исходной таблице заполнялось
 * почти всегда. Участник, магазин, контрагент и количество спрятаны: в
 * данных они появляются редко, и показывать четыре пустых столбца ради
 * случая, когда они пригодятся, — верный способ сделать таблицу
 * нечитаемой.
 */

export type ColumnId =
  | "date"
  | "description"
  | "category"
  | "account"
  | "amount"
  | "balance"
  | "participant"
  | "store"
  | "counterparty"
  | "tags"
  | "note"
  | "currency"
  | "uuid";

export interface ColumnSpec {
  id: ColumnId;
  /** Ключ строки перевода: заголовок колонки. Типизирован ключами
   * словаря, поэтому опечатка в нём — ошибка компиляции, а не пустая
   * шапка в готовой таблице. */
  labelKey: TranslationKey;
  /** Выравнивание содержимого. Числа — вправо, чтобы разряды выстроились. */
  align: "left" | "right";
  /** Колонку нельзя убрать: без неё строка перестаёт быть узнаваемой. */
  required?: boolean;
  /** Минимальная ширина в пикселях — таблица шире экрана скроллится вбок. */
  width: number;
}

export const COLUMNS: ColumnSpec[] = [
  { id: "date", labelKey: "transactions.columnDate", align: "left", required: true, width: 96 },
  { id: "description", labelKey: "transactions.columnDescription", align: "left", required: true, width: 220 },
  { id: "category", labelKey: "transactions.columnCategory", align: "left", width: 180 },
  { id: "account", labelKey: "transactions.columnAccount", align: "left", width: 140 },
  { id: "amount", labelKey: "transactions.columnAmount", align: "right", required: true, width: 120 },
  { id: "balance", labelKey: "transactions.columnBalance", align: "right", width: 130 },
  { id: "participant", labelKey: "transactions.columnParticipant", align: "left", width: 120 },
  { id: "store", labelKey: "transactions.columnStore", align: "left", width: 140 },
  { id: "counterparty", labelKey: "transactions.columnCounterparty", align: "left", width: 140 },
  { id: "tags", labelKey: "transactions.columnTags", align: "left", width: 160 },
  { id: "note", labelKey: "transactions.columnNote", align: "left", width: 200 },
  { id: "currency", labelKey: "transactions.columnCurrency", align: "left", width: 80 },
  { id: "uuid", labelKey: "transactions.columnUuid", align: "left", width: 260 },
];

/** Видимые по умолчанию и в этом порядке. */
export const DEFAULT_VISIBLE: ColumnId[] = ["date", "description", "category", "account", "amount", "balance"];

export interface ColumnLayout {
  /** Порядок колонок — включая скрытые, чтобы возвращённая обратно колонка
   * встала на своё прежнее место, а не в конец. */
  order: ColumnId[];
  visible: ColumnId[];
}

export const DEFAULT_LAYOUT: ColumnLayout = {
  order: COLUMNS.map((column) => column.id),
  visible: DEFAULT_VISIBLE,
};

/**
 * Приводит сохранённую раскладку к текущему набору колонок.
 *
 * Раскладка лежит в localStorage и переживает обновления приложения, в
 * которых колонки добавляются и исчезают. Без этой сверки старая запись
 * либо потеряет новую колонку навсегда, либо попытается отрисовать давно
 * удалённую.
 */
export function reconcileLayout(stored: Partial<ColumnLayout> | null | undefined): ColumnLayout {
  const known = new Set(COLUMNS.map((column) => column.id));
  const storedOrder = (stored?.order ?? []).filter((id): id is ColumnId => known.has(id as ColumnId));
  const missing = COLUMNS.map((column) => column.id).filter((id) => !storedOrder.includes(id));
  const order = [...storedOrder, ...missing];

  const storedVisible = stored?.visible?.filter((id): id is ColumnId => known.has(id as ColumnId));
  const visible = storedVisible?.length ? storedVisible : DEFAULT_VISIBLE;

  // Обязательные колонки возвращаются, даже если в сохранённой раскладке их
  // не было: строка без даты и суммы не читается.
  const required = COLUMNS.filter((column) => column.required).map((column) => column.id);
  const withRequired = [...new Set([...visible, ...required])];

  return { order, visible: order.filter((id) => withRequired.includes(id)) };
}

/** Значение ячейки в виде простого текста — для колонок, которым не нужна
 * собственная разметка. Возвращает null, если показывать нечего. */
export function plainCellValue(column: ColumnId, tx: Transaction): string | null {
  switch (column) {
    case "participant":
      return tx.participant_id ? String(tx.participant_id) : null;
    case "store":
      return tx.store_id ? String(tx.store_id) : null;
    case "counterparty":
      return tx.counterparty_id ? String(tx.counterparty_id) : null;
    case "note":
      return tx.notes;
    case "currency":
      return tx.currency;
    case "uuid":
      return tx.uuid;
    default:
      return null;
  }
}
