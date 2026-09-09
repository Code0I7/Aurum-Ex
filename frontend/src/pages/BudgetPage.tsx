import { useState } from "react";
import { Plus } from "lucide-react";
import { PageActions } from "@/components/layout/PageActions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { AlertBanner } from "@/components/insights/AlertBanner";
import { BudgetList } from "@/components/budget/BudgetList";
import { BudgetFormModal } from "@/components/budget/BudgetFormModal";
import { useBudgets, useBudgetStatus, useDeleteBudget } from "@/hooks/useBudgets";
import { useTransactionYears } from "@/hooks/useTransactions";
import { useTranslation } from "@/lib/i18n";
import { useSessionState } from "@/hooks/useSessionState";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { Budget, BudgetStatus } from "@/types";

export function BudgetPage() {
  const { t } = useTranslation();
  const now = new Date();
  const [year, setYear] = useSessionState("aurum:budget-year", now.getFullYear());
  const [month, setMonth] = useSessionState("aurum:budget-month", now.getMonth() + 1);
  const { data: years } = useTransactionYears();

  const { data: budgets } = useBudgets();
  const { data: status, isLoading } = useBudgetStatus(year, month);
  const deleteBudget = useDeleteBudget();
  const confirm = useConfirm();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingBudget, setEditingBudget] = useState<Budget | null>(null);

  function openCreateModal() {
    setEditingBudget(null);
    setModalOpen(true);
  }

  function openEditModal(item: BudgetStatus) {
    // Строка из плана сюда не приходит: у неё вместо кнопки правки ссылка в
    // «Планирование». Проверка на всякий случай — чтобы будущая кнопка не
    // открыла окно правки того, чего в бюджетах нет.
    if (item.budget_id === null) return;
    setEditingBudget({
      id: item.budget_id,
      category_id: item.category_id,
      category_name: item.category_name,
      category_color: item.category_color,
      category_icon: item.category_icon,
      monthly_limit: item.monthly_limit,
    });
    setModalOpen(true);
  }

  async function handleDelete(item: BudgetStatus) {
    const ok = await confirm({
      message: t("budget.confirmDelete", { name: translateCategoryName(item.category_name) }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (ok && item.budget_id !== null) deleteBudget.mutate(item.budget_id);
  }

  return (
    <div className="space-y-5">
      <AlertBanner />

      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <MonthSelector month={month} onChange={setMonth} />
        </div>
        <YearSelector years={years ?? [now.getFullYear()]} year={year} onChange={setYear} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("nav.budget")}</CardTitle>
          <PageActions>
            <Button onClick={openCreateModal}>
              <Plus size={16} />
              {t("common.add")}
            </Button>
          </PageActions>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <BudgetList items={status?.items ?? []} onEdit={openEditModal} onDelete={handleDelete} />
          )}
        </CardContent>
      </Card>

      <BudgetFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        budget={editingBudget}
        excludeCategoryIds={budgets?.map((budget) => budget.category_id) ?? []}
      />
    </div>
  );
}
