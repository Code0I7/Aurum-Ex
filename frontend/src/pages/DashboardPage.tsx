import { useState } from "react";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { StatCard } from "@/components/dashboard/StatCard";
import { SpendingByCategoryCard } from "@/components/dashboard/SpendingByCategoryCard";
import { RecentTransactionsCard } from "@/components/dashboard/RecentTransactionsCard";
import { AccountBalancesCard } from "@/components/dashboard/AccountBalancesCard";
import { LargestExpensesCard } from "@/components/dashboard/LargestExpensesCard";
import { MonthlyFlowCard } from "@/components/dashboard/MonthlyFlowCard";
import { AlertBanner } from "@/components/insights/AlertBanner";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { useTransactionYears } from "@/hooks/useTransactions";
import { formatCurrency, formatSignedCurrency, formatTransactionDate } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { DashboardRange } from "@/types";

/** Share of income left over after spending (net / real_income). `null` when
 * there was no income to take a share of, rather than a misleading 0%. */
function savingsRate(realIncome: number, net: number): number | null {
  return realIncome > 0 ? (net / realIncome) * 100 : null;
}

function formatPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(0)}%`;
}

export function DashboardPage() {
  const { t } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  // «За всё время» по умолчанию: при четырёх годах истории месяц —
  // случайный срез, и открываться на нём значит прятать почти всё, что
  // человек ввёл.
  const [range, setRange] = useState<DashboardRange>("all");
  const { data: years } = useTransactionYears();

  const { data, isLoading, isError } = useDashboardSummary(year, month, range);
  const rate = data ? savingsRate(Number(data.real_income), Number(data.net)) : null;

  const ranges: Array<{ key: DashboardRange; label: string }> = [
    { key: "month", label: t("dashboard.rangeMonth") },
    { key: "year", label: t("dashboard.rangeYear") },
    { key: "all", label: t("dashboard.rangeAll") },
  ];

  return (
    <div className="space-y-5">
      <AlertBanner excludeKeys={["risky_allocation_exceeded"]} />

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-1">
          {ranges.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setRange(item.key)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                range === item.key
                  ? "bg-surface-2 text-text-primary"
                  : "text-text-muted hover:bg-surface-2 hover:text-text-primary"
              }`}
            >
              {item.label}
            </button>
          ))}
          {/* Границы периода подписаны датами: при «за всё время» интерфейс
              сам не знает, с какого дня идёт история. */}
          {data?.start_date && data.end_date && (
            <span className="ml-auto text-xs text-text-muted">
              {formatTransactionDate(data.start_date, true)} — {formatTransactionDate(data.end_date, true)}
            </span>
          )}
        </div>

        {/* Выбор месяца и года прячется, когда он ни на что не влияет:
            переключатель, который ничего не меняет, — обещание, которого
            приложение не выполняет. */}
        {range !== "all" && (
          <div className="flex items-center gap-3">
            {range === "month" && (
              <div className="min-w-0 flex-1">
                <MonthSelector month={month} onChange={setMonth} />
              </div>
            )}
            <YearSelector years={years ?? [now.getFullYear()]} year={year} onChange={setYear} />
          </div>
        )}
      </div>

      {isError && (
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {t("dashboard.errorLoading")}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard
          label={t("dashboard.statRealIncomeLabel")}
          value={isLoading ? "…" : formatCurrency(data?.real_income ?? 0)}
          caption={t("dashboard.statRealIncomeCaption")}
          tone="success"
        />
        <StatCard
          label={t("dashboard.statSpentLabel")}
          value={isLoading ? "…" : formatCurrency(data?.spent ?? 0)}
          caption={t("dashboard.statSpentCaption")}
          tone="danger"
        />
        <StatCard
          label={t("dashboard.statNetLabel")}
          value={isLoading ? "…" : formatSignedCurrency(data?.net ?? 0)}
          caption={t("dashboard.statNetCaption")}
          tone={Number(data?.net ?? 0) >= 0 ? "success" : "danger"}
        />
        {/* Заработок за час занимает место нормы сбережений, когда часы
            введены: он переводит покупки на язык времени — «монитор стоил
            четыре дня» доходит быстрее, чем «17 273 ₽». Без часов остаётся
            прежняя карточка. */}
        {data?.earned_per_hour ? (
          <StatCard
            label={t("dashboard.statHourlyLabel")}
            value={formatCurrency(data.earned_per_hour)}
            caption={t("dashboard.statHourlyCaption", { hours: Number(data.hours_worked) })}
            tone="default"
          />
        ) : (
          <StatCard
            label={t("dashboard.statSavingsRateLabel")}
            value={isLoading ? "…" : rate === null ? "—" : formatPercent(rate)}
            caption={t("dashboard.statSavingsRateCaption")}
            tone={rate === null ? "default" : rate >= 0 ? "success" : "danger"}
          />
        )}
      </div>

      <MonthlyFlowCard points={data?.monthly ?? []} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
        <SpendingByCategoryCard items={data?.spending_by_category ?? []} />
        <div className="space-y-4">
          <AccountBalancesCard accounts={data?.accounts ?? []} />
          <LargestExpensesCard items={data?.largest_expenses ?? []} />
        </div>
      </div>

      <RecentTransactionsCard year={year} month={month} />
    </div>
  );
}
