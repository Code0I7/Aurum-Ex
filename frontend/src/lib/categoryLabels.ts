import { t, type TranslationKey } from "@/lib/i18n";

// Maps the exact seeded English category name (backend/app/db/seed.py) to
// its translation key, so the fixed default set reads in the user's chosen
// language regardless of what the DB literally stores. Categories created
// through the category-management UI (CategoriesPage) aren't in this map —
// their name is whatever the user typed and is shown as-is.
const DEFAULT_CATEGORY_KEYS: Record<string, TranslationKey> = {
  "Housing & Utilities": "category.housingUtilities",
  Groceries: "category.groceries",
  "Dining Out": "category.diningOut",
  Transportation: "category.transportation",
  "Health & Fitness": "category.healthFitness",
  Shopping: "category.shopping",
  Entertainment: "category.entertainment",
  Subscriptions: "category.subscriptions",
  Salary: "category.salary",
  Freelance: "category.freelance",
  Investments: "category.investments",
  Gifts: "category.gifts",
  "Business Income": "category.businessIncome",
  "Rental Income": "category.rentalIncome",
  Benefits: "category.benefits",
  "Item Sales": "category.itemSales",
  "Other Income": "category.otherIncome",
};

export function translateCategoryName(name: string): string {
  const key = DEFAULT_CATEGORY_KEYS[name];
  return key ? t(key) : name;
}

/** A category's full path for display — "Groceries" alone reads as if it
 * were a top-level category even when it's actually a subcategory; showing
 * "Groceries · Sweets" makes the parent unambiguous everywhere a bare
 * category name used to be shown (transaction rows, filters). `categories`
 * is the full list (any kind, any order) to resolve ancestors from
 * `category.parent_id`.
 *
 * Поднимается до самого корня, а не на один шаг: ветки бывают глубже двух
 * уровней, и «Молочное · Сыр» без «Продуктов» отвечает на вопрос лишь
 * наполовину. Счётчик шагов — страховка от битой ссылки на родителя:
 * бесконечный цикл здесь повесил бы всю страницу. */
export function categoryPath(
  category: { name: string; parent_id: number | null },
  categories: { id: number; name: string; parent_id?: number | null }[] | undefined
): string {
  const chain = [translateCategoryName(category.name)];
  let parentId = category.parent_id;
  for (let step = 0; parentId != null && step < 10; step += 1) {
    const parent = categories?.find((c) => c.id === parentId);
    if (!parent) break;
    chain.unshift(translateCategoryName(parent.name));
    parentId = parent.parent_id ?? null;
  }
  return chain.join(" · ");
}

/** Отступ перед названием в выпадающем списке. Ветка глубиной в три
 * уровня без него читается как три равноправные категории подряд. */
export function categoryOptionPrefix(depth: number): string {
  return depth > 0 ? `${"\u00a0\u00a0\u00a0\u00a0".repeat(depth)}↳ ` : "";
}

/** Orders a category list for display in a dropdown: alphabetical by
 * translated name, with each subcategory placed directly under its own
 * parent (not scattered by name) and carrying its `depth` so callers can
 * indent it. Shared by every category picker (TransactionFormModal, the
 * Transactions/Reports filters) so they all read the same way.
 *
 * Обход рекурсивный, потому что дерево глубже одного уровня. Раньше
 * выписывались только корни и их прямые дети — и категория третьего уровня
 * («Продукты → Молочное → Сыр») не появлялась ни в одном списке вообще: ни
 * выбрать при вводе операции, ни отфильтровать по ней.
 *
 * Сирота — категория, чей родитель не попал в переданный список, например
 * при фильтре по виду, — выводится на верхнем уровне, а не пропадает.
 * Потеряться при показе хуже, чем оказаться не на своём отступе. */
export function buildHierarchicalCategories<C extends { id: number; parent_id: number | null; name: string }>(
  categories: C[],
  language: string
): (C & { indented: boolean; depth: number })[] {
  const sorted = [...categories].sort((a, b) =>
    translateCategoryName(a.name).localeCompare(translateCategoryName(b.name), language)
  );
  const known = new Set(sorted.map((category) => category.id));
  const result: (C & { indented: boolean; depth: number })[] = [];

  function walk(parentId: number | null, depth: number) {
    for (const category of sorted) {
      const effectiveParent =
        category.parent_id !== null && known.has(category.parent_id) ? category.parent_id : null;
      if (effectiveParent !== parentId) continue;
      result.push({ ...category, indented: depth > 0, depth });
      walk(category.id, depth + 1);
    }
  }

  walk(null, 0);
  return result;
}
