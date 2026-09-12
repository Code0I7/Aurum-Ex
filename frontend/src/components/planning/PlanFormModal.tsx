import { useEffect, useState } from "react";
import { Archive, ArchiveRestore, Plus, Trash2 } from "lucide-react";
import { CategoryPicker } from "@/components/categories/CategoryPicker";
import { RecurrenceEditor } from "@/components/planning/RecurrenceEditor";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { useCreatePlan, useUpdatePlan } from "@/hooks/usePlans";
import { useCategories } from "@/hooks/useCategories";
import { useTranslation } from "@/lib/i18n";
import { DEFAULT_RECURRENCE, type Recurrence } from "@/lib/recurrence";
import type { Plan } from "@/types";

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
  is_archived: boolean;
}

function emptyPeriod(validFrom = ""): PeriodRow {
  return {
    key: crypto.randomUUID(),
    amount: "",
    valid_from: validFrom,
    valid_to: "",
    note: "",
    is_archived: false,
  };
}

const EMPTY_FORM = {
  category_id: "",
  note: "",
};

export function PlanFormModal({ open, onClose, plan }: PlanFormModalProps) {
  const { t } = useTranslation();
  const createPlan = useCreatePlan();
  const updatePlan = useUpdatePlan();
  const { data: categories } = useCategories();

  const [form, setForm] = useState(EMPTY_FORM);
  // Расписание держится отдельным куском состояния, а не полями формы:
  // правило целиком меняется при выборе пункта списка, и собирать его
  // обратно из десятка отдельных ключей пришлось бы в каждом обработчике.
  const [rule, setRule] = useState<Recurrence>(DEFAULT_RECURRENCE);
  const [periods, setPeriods] = useState<PeriodRow[]>([emptyPeriod()]);
  // Список отрезков растёт и не убывает: тариф менялся четыре раза за три
  // года — строк четыре, живая одна. Убранные в архив считаются ровно так
  // же, просто не мозолят глаза, пока не попросят показать.
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    if (plan) {
      setForm({
        category_id: plan.category_id?.toString() ?? "",
        note: plan.note ?? "",
      });
      setRule({
        kind: plan.kind,
        repeat_every: plan.repeat_every,
        weekdays: plan.weekdays,
        month_day_mode: plan.month_day_mode,
        month_days: plan.month_days,
        nth_weekday: plan.nth_weekday,
        months: plan.months,
        skip_weekends: plan.skip_weekends,
        workdays_only: plan.workdays_only,
      });
      setPeriods(
        plan.periods.map((period) => ({
          key: crypto.randomUUID(),
          amount: period.amount,
          valid_from: period.valid_from,
          valid_to: period.valid_to ?? "",
          note: period.note ?? "",
          is_archived: period.is_archived,
        }))
      );
    } else {
      // Новый план начинается с первого числа текущего месяца: план на
      // половину месяца всё равно действует на весь — см. plan_service.
      const now = new Date();
      const first = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
      setForm(EMPTY_FORM);
      setRule(DEFAULT_RECURRENCE);
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

  const archivedCount = periods.filter((row) => row.is_archived).length;
  const visiblePeriods = showArchived ? periods : periods.filter((row) => !row.is_archived);

  const isOneOff = rule.kind === "one_off";
  // «По отработанным дням» — не календарное правило, а факт из таблицы
  // времени: одно число на месяц, и умножать его на шаг не на что. Поэтому
  // галочка живёт только у плана «каждый день» и только без пропуска
  // выходных: вместе это означало бы два разных числа дней на один месяц.
  const canUseWorkdays = rule.kind === "day" && rule.repeat_every === 1 && !rule.skip_weekends;

  // Сумма всегда за одно повторение. Привычные подписи оставлены там, где
  // они верны: у дневного это сумма за день, у обычного ежемесячного — за
  // месяц, и переучивать человека ради единообразия незачем.
  const amountLabel = isOneOff
    ? t("planning.amountOnce")
    : rule.kind === "day"
      ? t("planning.amountPerDay")
      : rule.kind === "month" && rule.repeat_every === 1 && rule.month_day_mode === null
        ? t("planning.amountPerMonth")
        : t("planning.amountPerOccurrence");

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const input = {
      category_id: form.category_id ? Number(form.category_id) : null,
      kind: rule.kind,
      repeat_every: rule.repeat_every,
      weekdays: rule.weekdays,
      month_day_mode: rule.month_day_mode,
      month_days: rule.month_days,
      nth_weekday: rule.nth_weekday,
      months: rule.months,
      skip_weekends: rule.skip_weekends,
      periods: periods.map((row) => ({
        amount: row.amount,
        valid_from: row.valid_from,
        // Пустая дата окончания означает «пока не отменю», а не «сегодня».
        valid_to: row.valid_to || null,
        note: row.note || null,
        is_archived: row.is_archived,
      })),
      // Признак имеет смысл только у плана «каждый день» — бэкенд отклоняет
      // его на остальных, и посылать его оттуда было бы отправкой заведомой
      // ошибки.
      workdays_only: canUseWorkdays && rule.workdays_only,
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

        {/* Расписание целиком — своим блоком: полей у него больше, чем у
            всей остальной формы, и вперемешку с категорией и суммой они
            читались бы как одинаково важные. */}
        <RecurrenceEditor value={rule} onChange={setRule} />

        {/* Суммы списком. Категория и расписание у плана одни, а сумма
            меняется: подорожал тариф, сменился оператор. Раньше это
            означало второй план с тем же названием, и через несколько лет
            список планов превращался в список версий одного плана. */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>{t("planning.periods")}</Label>
            {/* У разового плана отрезок один по смыслу: он стоит в своём
                месяце и больше нигде, и второй был бы второй покупкой. */}
            {!isOneOff && (
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

          {/* Переключатель показа — только когда есть что показывать:
              галочка над пустотой заставляет искать, чего же она касается. */}
          {archivedCount > 0 && (
            <label className="flex items-center gap-2 text-xs text-text-muted">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(event) => setShowArchived(event.target.checked)}
                className="h-3.5 w-3.5 accent-text-primary"
              />
              {t("planning.showArchivedPeriods", { count: archivedCount })}
            </label>
          )}

          <ul className="space-y-2">
            {visiblePeriods.map((row, index) => (
              <li
                key={row.key}
                className={`rounded-lg border p-2.5 ${
                  row.is_archived ? "border-dashed border-border opacity-60" : "border-border"
                }`}
              >
                <div className="grid gap-2 sm:grid-cols-2">
                  <div>
                    <Label htmlFor={`plan-amount-${row.key}`}>{amountLabel}</Label>
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
                {!isOneOff && (
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

                <div className="mt-2 flex items-center gap-3">
                  {/* В архив, а не удалить: прошлые суммы нужны — без них
                      таблица прошлых лет соврёт. */}
                  <button
                    type="button"
                    onClick={() => updatePeriod(row.key, { is_archived: !row.is_archived })}
                    className="flex items-center gap-1 text-xs text-text-muted hover:text-text-primary"
                  >
                    {row.is_archived ? <ArchiveRestore size={13} /> : <Archive size={13} />}
                    {t(row.is_archived ? "planning.unarchivePeriod" : "planning.archivePeriod")}
                  </button>
                  {periods.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removePeriod(row.key)}
                      className="flex items-center gap-1 text-xs text-text-muted hover:text-danger"
                    >
                      <Trash2 size={13} />
                      {t("planning.removePeriod")}
                    </button>
                  )}
                </div>

                {/* Подсказка про открытый конец — только у последнего:
                    у остальных пустая дата окончания означает перехлёст, и
                    сервер её не примет. */}
                {index === visiblePeriods.length - 1 && !isOneOff && (
                  <p className="mt-2 text-xs text-text-muted">{t("planning.validToHint")}</p>
                )}
              </li>
            ))}
          </ul>
        </div>

        {/* Отработанные дни — не календарное правило, а факт из таблицы
            времени: он вводится руками и появляется задним числом, зато
            верен при любом графике, чего календарные «пн-пт» не дают ни
            вахте, ни суткам через двое. Поэтому галочка стоит здесь, а не
            среди расписания. */}
        {canUseWorkdays && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={rule.workdays_only}
              onChange={(event) =>
                setRule((prev) => ({ ...prev, workdays_only: event.target.checked }))
              }
              className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
            />
            <span>
              {t("planning.workdaysOnly")}
              <span className="block text-xs text-text-muted">{t("planning.workdaysOnlyHint")}</span>
            </span>
          </label>
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
