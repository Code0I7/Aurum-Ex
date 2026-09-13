import { categoryPath } from "@/lib/categoryLabels";
import { formatCurrency } from "@/lib/format";
import { getCategoryIcon } from "@/lib/icons";
import type { Category, TransactionSplit } from "@/types";

interface CategoryGroup {
  key: string;
  /** Путь до категории — «Продукты · Молочное · Сыр», как у одиночной. */
  path: string;
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
 * Подпись — полный путь, как у одиночной категории. Сначала здесь стояло
 * одно название, и разделённая операция выглядела беднее обычной: «Сыр»
 * вместо «Продукты · Молочное · Сыр», хотя вопрос у человека тот же.
 *
 * Порядок — по первому появлению категории, а не по алфавиту или сумме:
 * человек вводил доли в каком-то порядке, и перестановка при показе
 * выглядела бы так, будто запись изменилась.
 */
export function groupSplitCategories(
  splits: TransactionSplit[],
  categories: Category[] | undefined
): CategoryGroup[] {
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
      path: split.category ? categoryPath(split.category, categories) : "?",
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
 * Два расклада, потому что места для подписи бывает два:
 *
 * * **stack** — в ячейке сетки. Каждая категория на своей строке и получает
 *   всю ширину ячейки, как одиночная. Первая версия ставила их в одну строку,
 *   и ячейка в 280 точек делилась между долями: каждой доставался огрызок
 *   «Про…», и путь не помещался ни у одной. Цена — строка операции выше
 *   обычной, но читается каждая категория целиком;
 * * **inline** — в строке подписи компактного списка, где рядом дата, счёт и
 *   теги. Там переносить нельзя, и категории идут подряд, а обрезается вся
 *   строка в конце — как обрезается любой длинный текст в ней. Сжимать
 *   каждую долю по отдельности здесь нельзя по той же причине, что и в
 *   сетке.
 *
 * Сумма группы — в подсказке при наведении, а не в строке: число рядом с
 * каждым путём вытеснило бы сами пути.
 */
export function SplitCategories({
  splits,
  categories,
  currency,
  layout = "inline",
}: {
  splits: TransactionSplit[];
  /** Дерево категорий — чтобы собрать путь от корня. */
  categories: Category[] | undefined;
  /** Валюта операции: доли записаны в ней же. */
  currency?: string;
  layout?: "stack" | "inline";
}) {
  const groups = groupSplitCategories(splits, categories);

  if (layout === "stack") {
    return (
      <span className="flex min-w-0 flex-col gap-0.5">
        {groups.map((group) => {
          const Icon = getCategoryIcon(group.icon);
          return (
            <span
              key={group.key}
              className="flex min-w-0 items-center gap-1.5"
              title={`${group.path} · ${formatCurrency(group.total, currency)}`}
            >
              <Icon
                size={13}
                className="shrink-0"
                style={{ color: group.color ?? "var(--text-muted)" }}
                aria-hidden
              />
              <span className="truncate">{group.path}</span>
              {/* «×2» не обрезается: длинный путь уйдёт в многоточие, а
                  сколько раз категория встретилась, должно быть видно. */}
              {group.count > 1 && (
                <span className="shrink-0 tabular-nums text-text-muted">×{group.count}</span>
              )}
            </span>
          );
        })}
      </span>
    );
  }

  return (
    <>
      {groups.map((group, index) => {
        const Icon = getCategoryIcon(group.icon);
        return (
          // Между группами — отступ, а не разделитель-символ. Точка с
          // пробелами уже разделяет звенья пути внутри группы, и та же
          // точка между группами сделала бы границу неразличимой. Значок в
          // начале каждой группы и так показывает, где начинается следующая.
          <span
            key={group.key}
            className={index > 0 ? "ml-2" : undefined}
            title={`${group.path} · ${formatCurrency(group.total, currency)}`}
          >
            <Icon
              size={12}
              className="mr-0.5 inline-block align-[-2px]"
              style={{ color: group.color ?? "var(--text-muted)" }}
              aria-hidden
            />
            {group.path}
            {group.count > 1 && <span className="tabular-nums"> ×{group.count}</span>}
          </span>
        );
      })}
    </>
  );
}
