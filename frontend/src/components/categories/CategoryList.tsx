import { Pencil, Trash2 } from "lucide-react";
import { translateCategoryName } from "@/lib/categoryLabels";
import { getCategoryIcon } from "@/lib/icons";
import { useTranslation } from "@/lib/i18n";
import type { Category } from "@/types";

interface CategoryListProps {
  items: Category[];
  onEdit: (category: Category) => void;
  onDelete: (category: Category) => void;
}

interface RowProps {
  category: Category;
  /** Глубина в дереве: 0 — корень. Задаёт отступ. */
  depth: number;
  onEdit: (category: Category) => void;
  onDelete: (category: Category) => void;
}

// Шаг отступа. Меньше, чем прежние 32px на один уровень: с пятью уровнями
// такой отступ съел бы половину ширины на телефоне.
const INDENT_STEP = 18;

function CategoryRow({ category, depth, onEdit, onDelete }: RowProps) {
  const { t } = useTranslation();
  const Icon = getCategoryIcon(category.icon);

  return (
    <li className="flex items-center gap-3 py-2.5" style={{ paddingLeft: depth * INDENT_STEP }}>
      <span
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
        style={{ backgroundColor: `${category.color}1a`, color: category.color }}
      >
        <Icon size={15} />
      </span>
      <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate text-sm font-medium text-text-primary">
        <span className="truncate">{translateCategoryName(category.name)}</span>
        {category.is_default && (
          <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
            {t("category.defaultBadge")}
          </span>
        )}
      </span>
      <span className="flex shrink-0 gap-1">
        <button
          type="button"
          aria-label={t("common.edit")}
          onClick={() => onEdit(category)}
          className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
        >
          <Pencil size={15} />
        </button>
        <button
          type="button"
          aria-label={t("common.delete")}
          onClick={() => onDelete(category)}
          className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
        >
          <Trash2 size={15} />
        </button>
      </span>
    </li>
  );
}

export function CategoryList({ items, onEdit, onDelete }: CategoryListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-6 text-center text-sm text-text-muted">{t("category.empty")}</p>;
  }

  // `items` приходит отсортированным (по алфавиту, из CategoriesPage).
  // Дерево обходится сверху вниз на любую глубину: раньше здесь было ровно
  // два уровня, и внук просто не отрисовывался бы.
  const byId = new Map(items.map((category) => [category.id, category]));
  const childrenOf = new Map<number | null, Category[]>();
  for (const category of items) {
    // Ребёнок, чей родитель не попал в список (отфильтровали по виду),
    // считается корневым — иначе он исчез бы с экрана вместе с ветвью.
    const key = category.parent_id !== null && byId.has(category.parent_id) ? category.parent_id : null;
    const bucket = childrenOf.get(key);
    if (bucket) bucket.push(category);
    else childrenOf.set(key, [category]);
  }

  const rows: { category: Category; depth: number }[] = [];
  const visited = new Set<number>();
  function walk(parentId: number | null, depth: number) {
    for (const category of childrenOf.get(parentId) ?? []) {
      // Защита от цикла в данных: бэкенд его не допускает, но испорченная
      // база не должна вешать страницу бесконечной рекурсией.
      if (visited.has(category.id)) continue;
      visited.add(category.id);
      rows.push({ category, depth });
      walk(category.id, depth + 1);
    }
  }
  walk(null, 0);

  return (
    <ul className="divide-y divide-gridline">
      {rows.map(({ category, depth }) => (
        <CategoryRow key={category.id} category={category} depth={depth} onEdit={onEdit} onDelete={onDelete} />
      ))}
    </ul>
  );
}
