import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { CategoryPicker } from "@/components/categories/CategoryPicker";
import { useCategories } from "@/hooks/useCategories";
import { useCreateBudget, useUpdateBudget } from "@/hooks/useBudgets";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { Budget } from "@/types";

interface BudgetFormModalProps {
  open: boolean;
  onClose: () => void;
  budget?: Budget | null;
  /** Expense categories that already have a budget — excluded from the
   * create picker since each category can only carry one budget. */
  excludeCategoryIds: number[];
}

export function BudgetFormModal({ open, onClose, budget, excludeCategoryIds }: BudgetFormModalProps) {
  const { t } = useTranslation();
  const { data: categories } = useCategories();
  const createBudget = useCreateBudget();
  const updateBudget = useUpdateBudget();

  const [categoryId, setCategoryId] = useState("");
  const [monthlyLimit, setMonthlyLimit] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Порядок и дерево строит сам выбиратель — здесь только отбор. Своя
  // сортировка по имени рассыпала бы ветки: подкатегория вставала бы между
  // чужими корнями.
  const availableCategories = (categories ?? []).filter(
    (category) => category.kind === "expense" && !excludeCategoryIds.includes(category.id)
  );

  useEffect(() => {
    if (!open) return;
    if (budget) {
      setCategoryId(String(budget.category_id));
      setMonthlyLimit(budget.monthly_limit);
    } else {
      setCategoryId(availableCategories[0] ? String(availableCategories[0].id) : "");
      setMonthlyLimit("");
    }
    setError(null);
    // availableCategories is derived from `categories`, not a stable dep — only re-run on open/budget change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, budget]);

  const isSaving = createBudget.isPending || updateBudget.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    try {
      if (budget) {
        await updateBudget.mutateAsync({ id: budget.id, monthlyLimit });
      } else {
        await createBudget.mutateAsync({ category_id: Number(categoryId), monthly_limit: monthlyLimit });
      }
      onClose();
    } catch {
      setError(t("budget.form.saveError"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={budget ? t("budget.form.editTitle") : t("budget.form.newTitle")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="budget-category">{t("budget.form.categoryLabel")}</Label>
          {budget ? (
            <p className="text-sm text-text-primary">{translateCategoryName(budget.category_name)}</p>
          ) : availableCategories.length === 0 ? (
            <p className="text-sm text-text-muted">{t("budget.form.noCategoriesAvailable")}</p>
          ) : (
            <CategoryPicker
              id="budget-category"
              categories={availableCategories}
              value={categoryId}
              onChange={setCategoryId}
              placeholder={t("budget.form.categoryLabel")}
            />
          )}
        </div>

        <div>
          <Label htmlFor="budget-limit">{t("budget.form.limitLabel")}</Label>
          <Input
            id="budget-limit"
            type="number"
            step="0.01"
            min="0.01"
            required
            value={monthlyLimit}
            onChange={(event) => setMonthlyLimit(event.target.value)}
          />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving || (!budget && availableCategories.length === 0)}>
            {isSaving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
