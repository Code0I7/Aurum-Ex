import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Combobox } from "@/components/ui/Combobox";
import { CategoryPicker } from "@/components/categories/CategoryPicker";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { useCreatePlan, useUpdatePlan } from "@/hooks/usePlans";
import { useCategories } from "@/hooks/useCategories";
import { useTranslation } from "@/lib/i18n";
import type { Plan, PlanKind } from "@/types";

/** Следующий день после даты в виде ГГГГ-ММ-ДД. Нужен, чтобы новый
 *  отрезок начинался там, где кончился предыдущий, не перекрывая его
 *  ни на сутки: перехлёст сервер не примет. */
function nextDay(date: string): string {
  const parsed = new Date(`${date}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return "";
  parsed.setDate(parsed.getDate() + 1);
  return parsed.toISOString().slice(0, 10);
}

interface PlanFormModalProps {
  open: boolean;
  onClose: () => void;
  plan?: Plan | null;
}

/** Отрезок в состоянии формы: те же поля, что уходят на сервер, только
 *  строками — как их печатают в полях ввода. `key` живёт лишь в браузере:
 *  React нужен устойчивый ключ, а id у новой строки появится только после
 *  сохранения. */
interface PeriodRow {
  key: string;
  amount: string;
  valid_from: string;
  valid_to: string;
  note: string;
}

function emptyPeriod(validFrom = ""): PeriodRow {
  return { key: crypto.randomUUID(), amount: "", valid_from: validFrom, valid_to: "", note: "" };
}

const EMPTY_FORM = {
  category_id: "",
  kind: "monthly" as PlanKind,
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
  const [periods, setPeriods] = useState<PeriodRow[]>([emptyPeriod()]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    if (plan) {
      setForm({
        category_id: plan.category_id?.toString() ?? "",
        kind: plan.kind,
        workdays_only: plan.workdays_only,
        weekdays_only: plan.weekdays_only,
        note: plan.note ?? "",
      });
      setPeriods(
        plan.periods.map((period) => ({
          key: crypto.randomUUID(),
          amount: period.amount,
          valid_from: period.valid_from,
          valid_to: period.valid_to ?? "",
          note: period.note ?? "",
        }))
      );
    } else {
      // Новый план начинается с первого числа текущего месяца: план на
      // половину месяца всё равно действует на весь — см. plan_service.
      const now = new Date();
      const first = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
      setForm(EMPTY_FORM);
      setPeriods([emptyPeriod(first)]);
    }
  }, [open, plan]);

  function updatePeriod(key: string, patch: Partial<PeriodRow>) {
    setPeriods((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function addPeriod() {
    // Новый отрезок начинается там, где кончился предыдущий: смена тарифа
    // почти всегда именно так и выглядит, а поставить другую дату можно.
    const last = periods[periods.length - 1];
    const start = last?.valid_to ? nextDay(last.valid_to) : "";
    setPeriods((prev) => [...prev, emptyPeriod(start)]);
  }

  function removePeriod(key: string) {
    setPeriods((prev) => (prev.length > 1 ? prev.filter((row) => row.key !== key) : prev));
  }

  const isDaily = form.kind === "daily";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const input = {
      category_id: form.category_id ? Number(form.category_id) : null,
      kind: form.kind,
      periods: periods.map((row) => ({
        amount: row.amount,
        valid_from: row.valid_from,
        // Пустая дата окончания означает «пока не отменю», а не «сегодня».
        valid_to: row.valid_to || null,
        note: row.note || null,
      })),
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
          <Combobox
            id="plan-kind"
            className="mt-1"
            options={[
              { value: "monthly", label: t("planning.kind.monthly") },
              { value: "daily", label: t("planning.kind.daily") },
              { value: "one_off", label: t("planning.kind.oneOff") },
            ]}
            value={form.kind}
            onChange={(value) => setForm((prev) => ({ ...prev, kind: value as PlanKind }))}
            placeholder={t("planning.kind.monthly")}
          />
          <p className="mt-1 text-xs text-text-muted">{t(`planning.kindHint.${form.kind}` as never)}</p>
        </div>

        {/* Суммы списком. Категория и способ счёта у плана одни, а сумма
            меняется: подорожал тариф, сменился оператор. Раньше это
            означало второй план с тем же названием, и через несколько лет
            список планов превращался в список версий одного плана. */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>{t("planning.periods")}</Label>
            {/* У разового плана отрезок один по смыслу: он стоит в своём
                месяце и больше нигде, и второй был бы второй покупкой. */}
            {form.kind !== "one_off" && (
              <button
                type="button"
                onClick={addPeriod}
                className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                <Plus size={14} />
                {t("planning.addPeriod")}
              </button>
            )}
          </div>

          <ul className="space-y-2">
            {periods.map((row, index) => (
              <li key={row.key} className="rounded-lg border border-border p-2.5">
                <div className="grid gap-2 sm:grid-cols-2">
                  <div>
                    <Label htmlFor={`plan-amount-${row.key}`}>
                      {isDaily ? t("planning.amountPerDay") : t("planning.amountPerMonth")}
                    </Label>
                    <Input
                      id={`plan-amount-${row.key}`}
                      type="number"
                      step="0.01"
                      min="0.01"
                      required
                      value={row.amount}
                      onChange={(event) => updatePeriod(row.key, { amount: event.target.value })}
                    />
                  </div>
                  <div>
                    <Label htmlFor={`plan-from-${row.key}`}>{t("planning.validFrom")}</Label>
                    <Input
                      id={`plan-from-${row.key}`}
                      type="date"
                      required
                      value={row.valid_from}
                      onChange={(event) => updatePeriod(row.key, { valid_from: event.target.value })}
                    />
                  </div>
                </div>

                {/* Дата окончания скрыта у разового плана: он и так стоит в
                    одном месяце, и второе поле про то же самое путало бы. */}
                {form.kind !== "one_off" && (
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    <div>
                      <Label htmlFor={`plan-to-${row.key}`}>{t("planning.validTo")}</Label>
                      <Input
                        id={`plan-to-${row.key}`}
                        type="date"
                        value={row.valid_to}
                        onChange={(event) => updatePeriod(row.key, { valid_to: event.target.value })}
                      />
                    </div>
                    <div>
                      <Label htmlFor={`plan-note-${row.key}`}>{t("planning.periodNote")}</Label>
                      <Input
                        id={`plan-note-${row.key}`}
                        value={row.note}
                        placeholder={t("planning.periodNotePlaceholder")}
                        onChange={(event) => updatePeriod(row.key, { note: event.target.value })}
                      />
                    </div>
                  </div>
                )}

                {periods.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removePeriod(row.key)}
                    className="mt-2 flex items-center gap-1 text-xs text-text-muted hover:text-danger"
                  >
                    <Trash2 size={13} />
                    {t("planning.removePeriod")}
                  </button>
                )}

                {/* Подсказка про открытый конец — только у последнего:
                    у остальных пустая дата окончания означает перехлёст, и
                    сервер её не примет. */}
                {index === periods.length - 1 && form.kind !== "one_off" && (
                  <p className="mt-2 text-xs text-text-muted">{t("planning.validToHint")}</p>
                )}
              </li>
            ))}
          </ul>
        </div>

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
