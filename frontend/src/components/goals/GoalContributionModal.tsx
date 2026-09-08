import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { useAddGoalContribution } from "@/hooks/useGoals";
import { useAccounts } from "@/hooks/useAccounts";
import { useTranslation } from "@/lib/i18n";
import type { Goal } from "@/types";

interface GoalContributionModalProps {
  open: boolean;
  onClose: () => void;
  goal: Goal | null;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export function GoalContributionModal({ open, onClose, goal }: GoalContributionModalProps) {
  const { t } = useTranslation();
  const addContribution = useAddGoalContribution();

  const { data: accounts } = useAccounts(false);
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayIso());
  const [accountId, setAccountId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setAmount("");
    setDate(todayIso());
    // Счёт цели — разумное начальное значение: чаще всего копят с той же
    // карты, что и в прошлый раз.
    setAccountId(goal?.account_id ? String(goal.account_id) : "");
    setError(null);
  }, [open, goal]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!goal) return;
    setError(null);

    try {
      await addContribution.mutateAsync({
        id: goal.id,
        input: { amount, date, account_id: accountId ? Number(accountId) : null },
      });
      onClose();
    } catch (err) {
      // Единственный содержательный отказ — попытка вернуть с счёта
      // больше, чем с него откладывали. Сообщение об этом полезнее
      // общего «не удалось сохранить».
      setError(
        err instanceof Error && err.message.includes("more than was set aside")
          ? t("goal.contribution.tooMuchBack")
          : t("goal.contribution.saveError")
      );
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={goal ? t("goal.contribution.title", { name: goal.name }) : ""}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="contribution-amount">{t("goal.contribution.amountLabel")}</Label>
            <Input
              id="contribution-amount"
              type="number"
              step="0.01"
              required
              placeholder={t("goal.contribution.amountPlaceholder")}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="contribution-date">{t("goal.contribution.dateLabel")}</Label>
            <Input
              id="contribution-date"
              type="date"
              required
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
        </div>
        <div>
          <Label htmlFor="contribution-account">{t("goal.contribution.accountLabel")}</Label>
          <Select
            id="contribution-account"
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
          >
            <option value="">{t("goal.contribution.noAccount")}</option>
            {(accounts ?? []).map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
        </div>

        <p className="text-xs text-text-muted">{t("goal.contribution.hint")}</p>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={addContribution.isPending}>
            {addContribution.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
