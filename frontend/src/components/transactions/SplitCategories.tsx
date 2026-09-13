import { translateCategoryName } from "@/lib/categoryLabels";
import { formatCurrency } from "@/lib/format";
import { getCategoryIcon } from "@/lib/icons";
import type { TransactionSplit } from "@/types";

interface CategoryGroup {
  key: string;
  name: string;
  icon: string | null;
  color: string | null;
  count: number;
  total: number;
}

/**
 * Доли разбивки, сложенные по категориям.
 *
 * Раньше доли печатались подряд через плюс, и «Продукты + Продукты» читалось
 * как две разные вещи, хотя это одна категория, записанная двумя строками —
 * например, две позиции одного чека. Складываются они здесь, а не на сервере:
 * это вопрос отображения, а сами доли в операции остаются как записаны.
 *
 * Порядок — по первому появлению категории, а не по алфавиту или сумме:
 * человек вводил доли в каком-то порядке, и перестановка при показе
 * выглядела бы так, будто запись изменилась.
 */
export function groupSplitCategories(splits: TransactionSplit[]): CategoryGroup[] {
  const groups = new Map<string, CategoryGroup>();
  for (const split of splits) {
    // Удалённая категория — отдельной группой «?»: сложить её с какой-то
    // из живых значило бы приписать ей чужое имя.
    const key = split.category_id !== null ? String(split.category_id) : "none";
    const existing = groups.get(key);
    if (existing) {
      existing.count += 1;
      existing.total += Number(split.amount);
      continue;
    }
    groups.set(key, {
      key,
      name: split.category ? translateCategoryName(split.category.name) : "?",
      icon: split.category?.icon ?? null,
      color: split.category?.color ?? null,
      count: 1,
      total: Number(split.amount),
    });
  }
  return [...groups.values()];
}

/**
 * Категории разделённой операции: значок у каждой, повторы свёрнуты в «×2».
 *
 * Значок у каждой категории, а не один на всю строку. Прежде у разбивки
 * значка не было вовсе — «категорий несколько, и любая выбранная означала бы,
 * что остальные менее важны». Значок у каждой снимает этот вопрос: никто не
 * выбран, все на равных.
 *
 * Сумма группы — в подсказке при наведении, а не в строке: колонка категорий
 * узкая, и число рядом с каждым названием вытеснило бы сами названия.
 */
export function SplitCategories({
  splits,
  currency,
}: {
  splits: TransactionSplit[];
  /** Валюта операции: доли записаны в ней же. */
  currency?: string;
}) {
  const groups = groupSplitCategories(splits);
  return (
    <span className="inline-flex min-w-0 items-center gap-2 align-middle">
      {groups.map((group) => {
        const Icon = getCategoryIcon(group.icon);
        return (
          <span
            key={group.key}
            className="inline-flex min-w-0 items-center gap-1"
            title={`${group.name} · ${formatCurrency(group.total, currency)}`}
          >
            <Icon
              size={13}
              className="shrink-0"
              style={{ color: group.color ?? "var(--text-muted)" }}
              aria-hidden
            />
            <span className="truncate">{group.name}</span>
            {group.count > 1 && (
              <span className="shrink-0 tabular-nums text-text-muted">×{group.count}</span>
            )}
          </span>
        );
      })}
    </span>
  );
}
