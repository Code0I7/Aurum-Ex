import { useMemo, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { PageActions } from "@/components/layout/PageActions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { PlanTable } from "@/components/planning/PlanTable";
import { PlanFormModal } from "@/components/planning/PlanFormModal";
import { WorkDaysCard } from "@/components/planning/WorkDaysCard";
import { WatchlistCard } from "@/components/planning/WatchlistCard";
import { useDeletePlan, usePlanOverview, usePlans } from "@/hooks/usePlans";
import { useTranslation } from "@/lib/i18n";
import { useSessionState } from "@/hooks/useSessionState";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { formatCurrency } from "@/lib/format";
import type { Plan } from "@/types";

/**
 * Планирование — год целиком.
 *
 * Отличается от бюджета, и обе вкладки существуют. Бюджет отвечает на
 * вопрос «не перебрал ли я прямо сейчас», планирование — «каким получится
 * год». Свести их значило бы заставить выбирать между предупреждением и
 * прогнозом.
 */
/** Отрезки плана, задевающие этот год. */
function periodsOfYear(plan: Plan, year: number) {
  const yearStart = `${year}-01-01`;
  const yearEnd = `${year}-12-31`;
  return plan.periods.filter(
    (period) => period.valid_from <= yearEnd && (period.valid_to === null || period.valid_to >= yearStart)
  );
}

function periodsInYear(plan: Plan, year: number): number {
  return periodsOfYear(plan, year).length;
}

/** Сумма, которой план описывается в этом году: последняя из
 *  действующих. Если их несколько, рядом стоит счётчик — одно число
 *  вместо двух иначе выглядело бы как весь план. */
function currentAmount(plan: Plan, year: number): string {
  const periods = periodsOfYear(plan, year);
  return periods.length > 0 ? periods[periods.length - 1].amount : "0";
}

export function PlanningPage() {
  const { t } = useTranslation();
  const [year, setYear] = useSessionState("aurum:planning-year", new Date().getFullYear());
  const { data: overview, isLoading } = usePlanOverview(year);
  const { data: plans } = usePlans();
  const deletePlan = useDeletePlan();
  const confirm = useConfirm();

  // Только планы, действующие в выбранном году. Плана «связь 700 ₽»
  // хватает на годы, но за пять лет список копится из всего, что когда-то
  // было: отменённые тарифы, разовые покупки позапрошлого года, всё разом.
  // Таблица над списком показывает один год — список под ней обязан
  // показывать его же.
  //
  // Период считается пересекающимся, если он захватывает хотя бы один день
  // года: план с 01.11.2025 по 30.03.2026 виден и в 2025-м, и в 2026-м.
  const plansThisYear = useMemo(() => {
    const yearStart = `${year}-01-01`;
    const yearEnd = `${year}-12-31`;
    // План виден в году, если в него попадает хотя бы один его отрезок:
    // суммы теперь лежат списком, и «когда действует план» — это «когда
    // действует любая из его сумм».
    return (plans ?? []).filter((plan) =>
      plan.periods.some(
        (period) =>
          period.valid_from <= yearEnd && (period.valid_to === null || period.valid_to >= yearStart)
      )
    );
  }, [plans, year]);

  const [formOpen, setFormOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<Plan | null>(null);

  function openCreate() {
    setEditingPlan(null);
    setFormOpen(true);
  }

  function openEdit(plan: Plan) {
    setEditingPlan(plan);
    setFormOpen(true);
  }

  async function handleDelete(plan: Plan) {
    const ok = await confirm({
      message: t("planning.confirmDelete"),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (ok) deletePlan.mutate(plan.id);
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="items-start">
          <div>
            <CardTitle>{t("nav.planning")}</CardTitle>
            {/* Описание раздела живёт в подсказке (!) в шапке — тот же
                текст двумя местами расходится при первой правке. */}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 rounded-md border border-border">
              <button
                type="button"
                onClick={() => setYear((value) => value - 1)}
                className="px-2.5 py-1.5 text-sm text-text-muted hover:text-text-primary"
                aria-label={t("planning.previousYear")}
              >
                ‹
              </button>
              <span className="min-w-[3.5rem] text-center text-sm font-medium tabular-nums">{year}</span>
              <button
                type="button"
                onClick={() => setYear((value) => value + 1)}
                className="px-2.5 py-1.5 text-sm text-text-muted hover:text-text-primary"
                aria-label={t("planning.nextYear")}
              >
                ›
              </button>
            </div>
            <PageActions>
              <Button onClick={openCreate}>
                <Plus size={16} />
                {t("common.add")}
              </Button>
            </PageActions>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading || !overview ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : overview.rows.length === 0 ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("planning.empty")}</p>
          ) : (
            <PlanTable overview={overview} />
          )}
        </CardContent>
      </Card>

      {/* Список наблюдения — под таблицей года: сначала картина целиком,
          потом те несколько категорий, за которыми следят отдельно. */}
      <WatchlistCard year={year} />

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("planning.plansTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            {plansThisYear.length === 0 ? (
              <p className="py-6 text-center text-sm text-text-muted">{t("planning.noPlansThisYear", { year })}</p>
            ) : (
              <ul className="divide-y divide-gridline">
                {plansThisYear.map((plan) => (
                  <li key={plan.id} className="flex items-center gap-3 py-2.5">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {plan.category_name ?? t("planning.noCategory")}
                      </span>
                      <span className="block truncate text-xs text-text-muted">
                        {t(`planning.kind.${plan.kind === "one_off" ? "oneOff" : plan.kind}` as never)}
                        {plan.workdays_only && ` · ${t("planning.workdaysShort")}`}
                        {plan.weekdays_only && ` · ${t("planning.weekdaysShort")}`}
                        {plan.note && ` · ${plan.note}`}
                      </span>
                    </span>
                    {/* Сумма отрезка, действующего в выбранном году. Их
                        может быть несколько — тогда рядом стоит счётчик: без
                        него строка показывала бы одно число там, где план на
                        год состоит из двух. */}
                    <span className="shrink-0 text-right text-sm tabular-nums">
                      {formatCurrency(currentAmount(plan, year))}
                      <span className="text-xs text-text-muted">
                        {plan.kind === "daily" ? t("planning.perDay") : t("planning.perMonth")}
                      </span>
                      {periodsInYear(plan, year) > 1 && (
                        <span className="block text-xs font-normal text-text-muted">
                          {t("planning.periodCount", { count: periodsInYear(plan, year) })}
                        </span>
                      )}
                    </span>
                    <span className="flex shrink-0 gap-1">
                      <button
                        type="button"
                        aria-label={t("common.edit")}
                        onClick={() => openEdit(plan)}
                        className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        type="button"
                        aria-label={t("common.delete")}
                        onClick={() => handleDelete(plan)}
                        className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                      >
                        <Trash2 size={15} />
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <WorkDaysCard year={year} />
      </div>

      <PlanFormModal open={formOpen} onClose={() => setFormOpen(false)} plan={editingPlan} />
    </div>
  );
}
