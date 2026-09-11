import { useEffect, useState } from "react";
import { CategoryPicker } from "@/components/categories/CategoryPicker";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { useCreatePlan, useUpdatePlan } from "@/hooks/usePlans";
import { useCategories } from "@/hooks/useCategories";
import { useTranslation } from "@/lib/i18n";
import type { Plan, PlanKind } from "@/types";

interface PlanFormModalProps {
  open: boolean;
  onClose: () => void;
  plan?: Plan | null;
}

const EMPTY_FORM = {
  category_id: "",
  kind: "monthly" as PlanKind,
  amount: "",
  valid_from: "",
  valid_to: "",
  workdays_only: false,
  weekdays_only: false,
  note: "",
};

export function PlanFormModal({ open, onClose, plan }: PlanFormModalProps) {
  const { t } = useTranslation();
  const createPlan = useCreatePlan();
  const updatePlan = useUpdatePlan();
  const { data: categories } = useCategories();

  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    if (plan) {
      setForm({
        category_id: plan.category_id?.toString() ?? "",
        kind: plan.kind,
        amount: plan.amount,
        valid_from: plan.valid_from,
        valid_to: plan.valid_to ?? "",
        workdays_only: plan.workdays_only,
        weekdays_only: plan.weekdays_only,
        note: plan.note ?? "",
      });
    } else {
      // Новый план начинается с первого числа текущего месяца: план на
      // половину месяца всё равно действует на весь — см. plan_service.
      const now = new Date();
      const first = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
      setForm({ ...EMPTY_FORM, valid_from: first });
    }
  }, [open, plan]);

  const isDaily = form.kind === "daily";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const input = {
      category_id: form.category_id ? Number(form.category_id) : null,
      kind: form.kind,
      amount: form.amount,
      valid_from: form.valid_from,
      valid_to: form.valid_to || null,
      // Признак имеет смысл только у ежедневного плана — бэкенд отклоняет
      // его на остальных, и посылать его оттуда было бы отправкой заведомой
      // ошибки.
      workdays_only: isDaily && form.workdays_only,
      weekdays_only: isDaily && form.weekdays_only,
      note: form.note || null,
    };

    try {
      if (plan) {
        await updatePlan.mutateAsync({ id: plan.id, input });
      } else {
        await createPlan.mutateAsync(input);
      }
      onClose();
    } catch {
      setError(t("planning.saveError"));
    }
  }

  const isSaving = createPlan.isPending || updatePlan.isPending;

  return (
    <Dialog open={open} onClose={onClose} title={plan ? t("planning.editPlan") : t("planning.newPlan")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="plan-category">{t("planning.category")}</Label>
          {/* Тот же выбиратель, что и в операции: дерево, поиск и полный
              путь в закрытом поле. Раньше вложенность изображалась одним
              тире перед именем, и «Зарплата» Ивана с «Зарплатой» Ольги в
              списке были неотличимы. */}
          <CategoryPicker
            id="plan-category"
            categories={categories ?? []}
            value={form.category_id}
            onChange={(value) => setForm((prev) => ({ ...prev, category_id: value }))}
            placeholder={t("planning.noCategory")}
            emptyLabel={t("planning.noCategory")}
          />
        </div>

        <div>
          <Label htmlFor="plan-kind">{t("planning.kind")}</Label>
          <select
            id="plan-kind"
            value={form.kind}
            onChange={(event) => setForm((prev) => ({ ...prev, kind: event.target.value as PlanKind }))}
            className="mt-1 w-full rounded-md border border-border bg-surface-1 px-3 py-2 text-sm"
          >
            <option value="monthly">{t("planning.kind.monthly")}</option>
            <option value="daily">{t("planning.kind.daily")}</option>
            <option value="one_off">{t("planning.kind.oneOff")}</option>
          </select>
          <p className="mt-1 text-xs text-text-muted">{t(`planning.kindHint.${form.kind}` as never)}</p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="plan-amount">
              {isDaily ? t("planning.amountPerDay") : t("planning.amountPerMonth")}
            </Label>
            <Input
              id="plan-amount"
              type="number"
              step="0.01"
              min="0.01"
              required
              value={form.amount}
              onChange={(event) => setForm((prev) => ({ ...prev, amount: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="plan-from">{t("planning.validFrom")}</Label>
            <Input
              id="plan-from"
              type="date"
              required
              value={form.valid_from}
              onChange={(event) => setForm((prev) => ({ ...prev, valid_from: event.target.value }))}
            />
          </div>
        </div>

        {/* Дата окончания скрыта у разового плана: он и так стоит в одном
            месяце, и второе поле про то же самое только путало бы. */}
        {form.kind !== "one_off" && (
          <div>
            <Label htmlFor="plan-to">{t("planning.validTo")}</Label>
            <Input
              id="plan-to"
              type="date"
              value={form.valid_to}
              onChange={(event) => setForm((prev) => ({ ...prev, valid_to: event.target.value }))}
            />
            <p className="mt-1 text-xs text-text-muted">{t("planning.validToHint")}</p>
          </div>
        )}

        {/* Два способа считать дни, и они взаимоисключающие: «отработанные»
            берутся из введённых руками work_periods, «будни» — из
            календаря. Включение одного снимает другое прямо здесь, а не
            четырёхсотым с сервера: человек не должен узнавать о
            несовместимости из ошибки сохранения. */}
        {isDaily && (
          <div className="space-y-2">
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.workdays_only}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    workdays_only: event.target.checked,
                    weekdays_only: event.target.checked ? false : prev.weekdays_only,
                  }))
                }
                className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
              />
              <span>
                {t("planning.workdaysOnly")}
                <span className="block text-xs text-text-muted">{t("planning.workdaysOnlyHint")}</span>
              </span>
            </label>

            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.weekdays_only}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    weekdays_only: event.target.checked,
                    workdays_only: event.target.checked ? false : prev.workdays_only,
                  }))
                }
                className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
              />
              <span>
                {t("planning.weekdaysOnly")}
                <span className="block text-xs text-text-muted">{t("planning.weekdaysOnlyHint")}</span>
              </span>
            </label>
          </div>
        )}

        <div>
          <Label htmlFor="plan-note">{t("planning.note")}</Label>
          <Input
            id="plan-note"
            placeholder={t("planning.notePlaceholder")}
            value={form.note}
            onChange={(event) => setForm((prev) => ({ ...prev, note: event.target.value }))}
          />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
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
