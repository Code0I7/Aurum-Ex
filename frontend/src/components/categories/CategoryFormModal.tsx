import { useEffect, useMemo, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { CategoryColorPicker } from "@/components/categories/CategoryColorPicker";
import { CategoryIconPicker } from "@/components/categories/CategoryIconPicker";
import { useCategories, useCreateCategory, useUpdateCategory } from "@/hooks/useCategories";
import { translateCategoryName } from "@/lib/categoryLabels";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { Category, CategoryKind } from "@/types";

interface CategoryFormModalProps {
  open: boolean;
  onClose: () => void;
  category?: Category | null;
  // Preselects kind for a new category — irrelevant once editing, since kind
  // can't change after creation (see backend CategoryUpdate schema).
  defaultKind: CategoryKind;
}

// Должно совпадать с MAX_DEPTH в backend/app/services/category_tree.py:
// предлагать вариант, на который сервер ответит отказом, бессмысленно.
const MAX_CATEGORY_DEPTH = 5;

const KINDS: CategoryKind[] = ["expense", "income"];

function emptyForm(kind: CategoryKind) {
  return { name: "", kind, icon: "wallet", color: "#2a78d6", parent_id: "" };
}

export function CategoryFormModal({ open, onClose, category, defaultKind }: CategoryFormModalProps) {
  const { t } = useTranslation();
  const { data: allCategories } = useCategories();
  const createCategory = useCreateCategory();
  const updateCategory = useUpdateCategory();

  const [form, setForm] = useState(emptyForm(defaultKind));
  const [error, setError] = useState<string | null>(null);
  // Распространить цвет и значок на всю ветку. Спрашивается, а не делается
  // молча: подкатегорию могли покрасить нарочно, и перекрасить её без
  // спроса значило бы стереть решение человека.
  const [applyToChildren, setApplyToChildren] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm(
      category
        ? {
            name: category.name,
            kind: category.kind,
            icon: category.icon ?? "wallet",
            color: category.color,
            parent_id: category.parent_id ? String(category.parent_id) : "",
          }
        : emptyForm(defaultKind)
    );
    setError(null);
  }, [open, category, defaultKind]);

  // Кандидаты в родители — всё дерево нужного вида, отсортированное как оно
  // выглядит, с отступом по глубине. Ветку с детьми теперь тоже можно
  // перенести целиком, поэтому отдельного запрета для неё нет.
  //
  // Из списка убирается сама категория и всё, что под ней: подвесить ветку
  // внутрь себя нельзя, и предлагать такой вариант, чтобы потом отказать,
  // бессмысленно. Глубже предела тоже не предлагаем — по той же причине.
  const parentCandidates = useMemo(() => {
    const all = allCategories ?? [];
    const childrenOf = new Map<number, Category[]>();
    for (const item of all) {
      if (item.parent_id === null) continue;
      const bucket = childrenOf.get(item.parent_id);
      if (bucket) bucket.push(item);
      else childrenOf.set(item.parent_id, [item]);
    }

    // Высота переносимой ветки: ветку из трёх уровней нельзя подвесить так,
    // чтобы её низ вышел за предел.
    function heightOf(id: number): number {
      let best = 1;
      for (const child of childrenOf.get(id) ?? []) best = Math.max(best, 1 + heightOf(child.id));
      return best;
    }
    const branchHeight = category ? heightOf(category.id) : 1;

    const forbidden = new Set<number>();
    if (category) {
      forbidden.add(category.id);
      const queue = [category.id];
      while (queue.length > 0) {
        const current = queue.pop()!;
        for (const child of childrenOf.get(current) ?? []) {
          forbidden.add(child.id);
          queue.push(child.id);
        }
      }
    }

    const result: Array<{ item: Category; depth: number }> = [];
    function walk(parentId: number | null, depth: number) {
      const level = all
        .filter((item) => item.parent_id === parentId && item.kind === form.kind)
        .sort((a, b) => a.name.localeCompare(b.name));
      for (const item of level) {
        if (!forbidden.has(item.id) && depth + 1 + branchHeight <= MAX_CATEGORY_DEPTH) {
          result.push({ item, depth });
        }
        walk(item.id, depth + 1);
      }
    }
    walk(null, 0);
    return result;
  }, [allCategories, category, form.kind]);

  // Вся ветка вниз, а не только прямые дети: перекрасить корень и оставить
  // внуков разноцветными — половина работы.
  const descendantCount = useMemo(() => {
    if (!category || !allCategories) return 0;
    const byParent = new Map<number, number[]>();
    for (const item of allCategories) {
      if (item.parent_id === null) continue;
      byParent.set(item.parent_id, [...(byParent.get(item.parent_id) ?? []), item.id]);
    }
    let count = 0;
    const queue = [category.id];
    while (queue.length > 0) {
      for (const child of byParent.get(queue.pop()!) ?? []) {
        count += 1;
        queue.push(child);
      }
    }
    return count;
  }, [allCategories, category]);

  const styleChanged =
    category !== null && category !== undefined && (form.color !== category.color || form.icon !== category.icon);

  const isSaving = createCategory.isPending || updateCategory.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const parent_id = form.parent_id ? Number(form.parent_id) : null;

    try {
      if (category) {
        await updateCategory.mutateAsync({
          id: category.id,
          input: {
            name: form.name,
            icon: form.icon,
            color: form.color,
            parent_id,
            apply_style_to_children: applyToChildren,
          },
        });
      } else {
        await createCategory.mutateAsync({ name: form.name, kind: form.kind, icon: form.icon, color: form.color, parent_id });
      }
      onClose();
    } catch {
      setError(t("category.form.saveError"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={category ? t("category.form.editTitle") : t("category.form.newTitle")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="category-name">{t("category.form.nameLabel")}</Label>
          <Input
            id="category-name"
            required
            placeholder={t("category.form.namePlaceholder")}
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="category-kind">{t("category.form.kindLabel")}</Label>
          <Select
            id="category-kind"
            value={form.kind}
            disabled={Boolean(category)}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, kind: event.target.value as CategoryKind, parent_id: "" }))
            }
          >
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {t(`category.kind.${kind}` as TranslationKey)}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <Label htmlFor="category-parent">{t("category.form.parentLabel")}</Label>
          <Select
            id="category-parent"
            value={form.parent_id}
            onChange={(event) => setForm((prev) => ({ ...prev, parent_id: event.target.value }))}
          >
            <option value="">{t("category.form.noParent")}</option>
            {parentCandidates.map(({ item, depth }) => (
              <option key={item.id} value={item.id}>
                {/* Неразрывные пробелы: обычные схлопываются в <option>, и
                    дерево превратилось бы в плоский список. */}
                {"  ".repeat(depth)}
                {depth > 0 ? "└ " : ""}
                {translateCategoryName(item.name)}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <Label>{t("category.form.iconLabel")}</Label>
          <CategoryIconPicker value={form.icon} onChange={(icon) => setForm((prev) => ({ ...prev, icon }))} />
        </div>

        <div>
          <Label>{t("category.form.colorLabel")}</Label>
          <CategoryColorPicker value={form.color} onChange={(color) => setForm((prev) => ({ ...prev, color }))} />
        </div>

        {/* Предложение появляется только когда есть что перекрашивать и
            есть что менять: у листа ветки нет, а без правки цвета или значка
            галочка ничего бы не делала. */}
        {category && descendantCount > 0 && styleChanged && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={applyToChildren}
              onChange={(event) => setApplyToChildren(event.target.checked)}
              className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
            />
            <span>
              {t("category.form.applyToChildren", { count: descendantCount })}
              <span className="block text-xs text-text-muted">
                {t("category.form.applyToChildrenHint")}
              </span>
            </span>
          </label>
        )}

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
