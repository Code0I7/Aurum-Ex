import { useEffect, useState } from "react";
import { Combobox } from "@/components/ui/Combobox";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { useCreateGoal, useUpdateGoal } from "@/hooks/useGoals";
import { useAccounts } from "@/hooks/useAccounts";
import { useTranslation } from "@/lib/i18n";
import type { Goal } from "@/types";

interface GoalFormModalProps {
  open: boolean;
  onClose: () => void;
  goal?: Goal | null;
}

const EMPTY_FORM = { name: "", target_amount: "", target_date: "", account_id: "" };

export function GoalFormModal({ open, onClose, goal }: GoalFormModalProps) {
  const { t } = useTranslation();
  const createGoal = useCreateGoal();
  const updateGoal = useUpdateGoal();
  const { data: accounts } = useAccounts(false);

  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (goal) {
      setForm({
        name: goal.name,
        target_amount: goal.target_amount,
        target_date: goal.target_date ?? "",
        account_id: goal.account_id?.toString() ?? "",
      });
    } else {
      setForm(EMPTY_FORM);
    }
    setError(null);
  }, [open, goal]);

  const isSaving = createGoal.isPending || updateGoal.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const input = {
      name: form.name,
      target_amount: form.target_amount,
      target_date: form.target_date || null,
      // Счёт необязателен: цель можно завести и до того, как решено, откуда
      // копить. Но пока он не указан, счёт не покажет «отложено» — деньги
      // обещаны, а откуда возьмутся, неизвестно.
      account_id: form.account_id ? Number(form.account_id) : null,
    };

    try {
      if (goal) {
        await updateGoal.mutateAsync({ id: goal.id, input });
      } else {
        await createGoal.mutateAsync(input);
      }
      onClose();
    } catch {
      setError(t("goal.form.saveError"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={goal ? t("goal.form.editTitle") : t("goal.form.newTitle")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="goal-name">{t("goal.form.nameLabel")}</Label>
          <Input
            id="goal-name"
            required
            placeholder={t("goal.form.namePlaceholder")}
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="goal-target">{t("goal.form.targetAmountLabel")}</Label>
            <Input
              id="goal-target"
              type="number"
              step="0.01"
              min="0.01"
              required
              value={form.target_amount}
              onChange={(event) => setForm((prev) => ({ ...prev, target_amount: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="goal-date">{t("goal.form.targetDateLabel")}</Label>
            <Input
              id="goal-date"
              type="date"
              value={form.target_date}
              onChange={(event) => setForm((prev) => ({ ...prev, target_date: event.target.value }))}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="goal-account">{t("goal.form.accountLabel")}</Label>
          <Combobox
            id="goal-account"
            className="mt-1"
            options={(accounts ?? []).map((account) => ({ value: String(account.id), label: account.name }))}
            value={form.account_id}
            onChange={(value) => setForm((prev) => ({ ...prev, account_id: value }))}
            placeholder={t("goal.form.accountNone")}
            emptyLabel={t("goal.form.accountNone")}
          />
          <p className="mt-1 text-xs text-text-muted">{t("goal.form.accountHint")}</p>
        </div>

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
