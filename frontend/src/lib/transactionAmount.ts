/**
 * Знак и цвет суммы операции — в одном месте на всё приложение.
 *
 * Развилка «плюс или минус» повторялась в каждом списке отдельно, и списки
 * разошлись: сетка на вкладке «Транзакции» знала про внешние расчёты, а
 * таблица в «Отчётах» и в результатах поиска — нет. Всё, что не перевод и
 * не расход, она считала приходом, поэтому подарок на 7 000 ₽ показывался
 * зелёным плюсом: деньги ушли человеку, а выглядело как заработок.
 *
 * Тип операции — не то же самое, что направление денег:
 *
 *   income        пришло       + зелёный
 *   external_in   пришло       + зелёный   (получено от человека)
 *   expense       ушло         − красный
 *   external_out  ушло         − красный   (передано человеку)
 *   transfer      никуда       без знака, серый
 *
 * Перевод остаётся серым намеренно: свои деньги переложены с одного счёта
 * на другой, ни потери, ни прибавления не произошло, и красный говорил бы
 * неправду.
 */
import type { TransactionType } from "@/types";

/** Куда двинулись деньги. Считать по нему, а не по типу операции. */
export type AmountDirection = "in" | "out" | "none";

export function amountDirection(type: TransactionType): AmountDirection {
  if (type === "income" || type === "external_in") return "in";
  if (type === "transfer") return "none";
  // expense и external_out — и всё, что появится в будущем как трата.
  return "out";
}

/** Знак перед числом. Минус — типографский, как в остальных списках. */
export function amountSign(type: TransactionType): string {
  const direction = amountDirection(type);
  return direction === "in" ? "+" : direction === "out" ? "−" : "";
}

/**
 * Класс цвета для суммы.
 *
 * `neutral` — чем красить перевод. В списке это приглушённый
 * серый, в таблице — пустота: там строка уже окрашена целиком, и
 * собственный серый у одной колонки выбивался бы из ряда.
 */
export function amountColorClass(type: TransactionType, neutral = "text-text-muted"): string {
  const direction = amountDirection(type);
  if (direction === "in") return "text-success";
  if (direction === "out") return "text-danger";
  return neutral;
}
