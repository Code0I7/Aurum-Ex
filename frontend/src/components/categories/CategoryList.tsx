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
  indented: boolean;
  onEdit: (category: Category) => void;
  onDelete: (category: Category) => void;
}

function CategoryRow({ category, indented, onEdit, onDelete }: RowProps) {
  const { t } = useTranslation();
  const Icon = getCategoryIcon(category.icon);

  return (
    <li className={`flex items-center gap-3 py-2.5 ${indented ? "pl-8" : ""}`}>
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

  // `items` arrives pre-sorted (alphabetically, by CategoriesPage) — walk
  // top-level categories in that order and splice each one's children in
  // directly beneath it, so a subcategory renders indented under its parent
  // while everything stays a single flat, evenly-divided list.
  const topLevel = items.filter((category) => category.parent_id === null);
  const topLevelIds = new Set(topLevel.map((category) => category.id));
  // Defensive only — a child whose parent got filtered out (e.g. a kind
  // mismatch) should never happen given the create/update validation, but
  // falls back to a top-level row instead of silently disappearing.
  const orphaned = items.filter((category) => category.parent_id !== null && !topLevelIds.has(category.parent_id));

  const rows: { category: Category; indented: boolean }[] = [];
  for (const parent of topLevel) {
    rows.push({ category: parent, indented: false });
    for (const child of items) {
      if (child.parent_id === parent.id) rows.push({ category: child, indented: true });
    }
  }
  for (const category of orphaned) rows.push({ category, indented: false });

  return (
    <ul className="divide-y divide-gridline">
      {rows.map(({ category, indented }) => (
        <CategoryRow key={category.id} category={category} indented={indented} onEdit={onEdit} onDelete={onDelete} />
      ))}
    </ul>
  );
}
