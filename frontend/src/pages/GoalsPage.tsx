import { useState } from "react";
import { Plus } from "lucide-react";
import { PageActions } from "@/components/layout/PageActions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { GoalList } from "@/components/goals/GoalList";
import { GoalFormModal } from "@/components/goals/GoalFormModal";
import { GoalContributionModal } from "@/components/goals/GoalContributionModal";
import { GoalHistoryModal } from "@/components/goals/GoalHistoryModal";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { useDeleteGoal, useGoals, useUpdateGoal } from "@/hooks/useGoals";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency } from "@/lib/format";
import type { Goal, GoalStatus } from "@/types";

export function GoalsPage() {
  const { t } = useTranslation();
  const { data: goals, isLoading } = useGoals();
  const deleteGoal = useDeleteGoal();
  const updateGoal = useUpdateGoal();
  const confirm = useConfirm();

  const [formOpen, setFormOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<Goal | null>(null);
  const [contributionOpen, setContributionOpen] = useState(false);
  const [contributingGoal, setContributingGoal] = useState<Goal | null>(null);
  // История открывается по самой цели, а не по флагу: модалка тянет её
  // взносы, и null здесь означает «закрыто» без второго состояния.
  const [historyGoal, setHistoryGoal] = useState<Goal | null>(null);

  function openCreateModal() {
    setEditingGoal(null);
    setFormOpen(true);
  }

  function openEditModal(goal: Goal) {
    setEditingGoal(goal);
    setFormOpen(true);
  }

  function openContributionModal(goal: Goal) {
    setContributingGoal(goal);
    setContributionOpen(true);
  }

  async function handleDelete(goal: Goal) {
    const ok = await confirm({
      message: t("goal.confirmDelete", { name: goal.name }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (ok) deleteGoal.mutate(goal.id);
  }

  /**
   * Завершение цели ничего не вычитает со счёта.
   *
   * Деньги уже ушли обычной тратой — вычесть их ещё раз значило бы
   * посчитать расход дважды. Исчезает только пометка: отрезок резерва на
   * полосе счёта.
   */
  async function handleStatusChange(goal: Goal, status: GoalStatus) {
    if (status !== "active") {
      const ok = await confirm({
        title: t(status === "achieved" ? "goal.markAchieved" : "goal.markCancelled"),
        message: t(status === "achieved" ? "goal.confirmAchieved" : "goal.confirmCancelled", {
          name: goal.name,
          amount: formatCurrency(goal.current_amount),
        }),
      });
      if (!ok) return;
    }
    updateGoal.mutate({ id: goal.id, input: { status } });
  }

  const active = (goals ?? []).filter((goal) => goal.status === "active");
  const closed = (goals ?? []).filter((goal) => goal.status !== "active");

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("goal.activeTitle")}</CardTitle>
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
            <GoalList
              items={active}
              onContribute={openContributionModal}
              onEdit={openEditModal}
              onHistory={setHistoryGoal}
              onDelete={handleDelete}
              onStatusChange={handleStatusChange}
            />
          )}
        </CardContent>
      </Card>

      {/* Завершённые не исчезают и не схлопываются в ноль: накопленное
          осталось историей, и «копил девять месяцев» — часть ответа на
          вопрос, чего эта покупка стоила. */}
      {closed.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t("goal.closedTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            <GoalList
              items={closed}
              onContribute={openContributionModal}
              onEdit={openEditModal}
              onHistory={setHistoryGoal}
              onDelete={handleDelete}
              onStatusChange={handleStatusChange}
            />
          </CardContent>
        </Card>
      )}

      <GoalFormModal open={formOpen} onClose={() => setFormOpen(false)} goal={editingGoal} />
      <GoalHistoryModal goal={historyGoal} onClose={() => setHistoryGoal(null)} />
      <GoalContributionModal
        open={contributionOpen}
        onClose={() => setContributionOpen(false)}
        goal={contributingGoal}
      />
    </div>
  );
}
