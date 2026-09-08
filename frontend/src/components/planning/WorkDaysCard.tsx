import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useSaveWorkPeriod, useWorkPeriods } from "@/hooks/usePlans";
import { useTranslation, getLanguage } from "@/lib/i18n";
import { getMonthLabels } from "@/lib/format";

/**
 * Отработанные часы и дни по месяцам года.
 *
 * Производственного календаря здесь нет намеренно: график у людей разный.
 * Сутки через двое, вахта, четыре дня в неделю — календарные «пн–пт»
 * неверны для всех них, а введённое человеком число верно всегда.
 *
 * Часы дают стоимость часа («эта покупка стоила полтора дня работы»), дни —
 * планы вида «столовая 300 ₽ в рабочий день».
 */
export function WorkDaysCard({ year }: { year: number }) {
  const { t } = useTranslation();
  const { data: periods } = useWorkPeriods(year);
  const savePeriod = useSaveWorkPeriod();
  const months = getMonthLabels(getLanguage());

  // Черновик правки — по одному месяцу за раз. Сохраняется по уходу из
  // поля: отдельная кнопка на двенадцать строк превратила бы ввод года в
  // двадцать четыре клика.
  const [draft, setDraft] = useState<Record<string, string>>({});

  function valueOf(month: number, field: "hours" | "workdays"): string {
    const key = `${month}-${field}`;
    if (key in draft) return draft[key];
    const period = periods?.find((item) => item.month === month);
    if (!period) return "";
    const value = field === "hours" ? period.hours : period.workdays;
    if (value === null || value === undefined) return "";
    // Часы приходят как "160.00" — хвост из нулей в поле ввода мешает.
    return field === "hours" ? String(Number(value)) : String(value);
  }

  function commit(month: number) {
    const hours = valueOf(month, "hours");
    const workdays = valueOf(month, "workdays");
    if (hours === "" && workdays === "") return;
    savePeriod.mutate({
      year,
      month,
      hours: hours === "" ? "0" : hours,
      // Пустое поле — это «не задано», а не ноль: ноль рабочих дней обнулил
      // бы план «в рабочий день», а не вернул бы его к календарным.
      workdays: workdays === "" ? null : Number(workdays),
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("planning.workTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-xs text-text-muted">{t("planning.workHint")}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-muted">
                <th className="py-2 pr-3 font-medium">{t("planning.month")}</th>
                <th className="px-2 py-2 text-right font-medium">{t("planning.hours")}</th>
                <th className="py-2 pl-2 text-right font-medium">{t("planning.workdays")}</th>
              </tr>
            </thead>
            <tbody>
              {months.map((label, index) => {
                const month = index + 1;
                return (
                  <tr key={label} className="border-b border-border/40 last:border-0">
                    <td className="py-1.5 pr-3 text-text-secondary">{label}</td>
                    {(["hours", "workdays"] as const).map((field) => (
                      <td key={field} className={field === "hours" ? "px-2 py-1.5" : "py-1.5 pl-2"}>
                        <input
                          type="number"
                          inputMode="decimal"
                          min="0"
                          step={field === "hours" ? "0.5" : "1"}
                          value={valueOf(month, field)}
                          onChange={(event) =>
                            setDraft((prev) => ({ ...prev, [`${month}-${field}`]: event.target.value }))
                          }
                          onBlur={() => commit(month)}
                          className="w-full rounded-md border border-border bg-surface-1 px-2 py-1 text-right text-sm tabular-nums"
                        />
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
