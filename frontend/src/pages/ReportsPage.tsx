import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Label, Select } from "@/components/ui/Input";
import { PillSelector } from "@/components/layout/PillSelector";
import { DateRangeSelector } from "@/components/layout/YearSelector";
import { CategoryRankingCard } from "@/components/reports/CategoryRankingCard";
import { CategorySpendingChart } from "@/components/reports/CategorySpendingChart";
import { TransactionsTable } from "@/components/transactions/TransactionsTable";
import { TransactionFormModal } from "@/components/transactions/TransactionFormModal";
import { useCategories } from "@/hooks/useCategories";
import { useCategoryRanking, useCategorySpendingReport } from "@/hooks/useReports";
import { useDeleteTransaction, useTransactions, useTransactionYears } from "@/hooks/useTransactions";
import type { TransactionSort } from "@/api/transactions";
import {
  computeRange,
  defaultCustomRange,
  type CustomDateRange,
  type RangePreset,
} from "@/lib/dateRange";
import { useSessionState } from "@/hooks/useSessionState";
import { useTranslation } from "@/lib/i18n";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { CategoryPicker } from "@/components/categories/CategoryPicker";
import type { Transaction } from "@/types";

const PAGE_SIZE = 20;

export function ReportsPage() {
  const { t } = useTranslation();
  const now = new Date();
  const RANGE_OPTIONS: Array<{ value: RangePreset; label: string }> = [
    { value: "all", label: t("reports.rangeAll") },
    { value: "this_year", label: t("reports.rangeThisYear") },
    { value: "5y", label: t("reports.range5y") },
    { value: "custom", label: t("reports.rangeCustom") },
  ];
  const { data: categories } = useCategories();
  const { data: years } = useTransactionYears();
  const [categoryId, setCategoryId] = useSessionState<number | null>("aurum:reports-category", null);
  const [range, setRange] = useSessionState<RangePreset>("aurum:reports-range", "all");
  // Ключ сменился вместе с формой значения: в старом лежит {fromYear,
  // toYear}, и прочитанное как {from, to} ушло бы на сервер пустым.
  const [customRange, setCustomRange] = useSessionState<CustomDateRange>(
    "aurum:reports-dates",
    defaultCustomRange(now)
  );
  const [sort, setSort] = useState<TransactionSort>("date_desc");
  const [page, setPage] = useState(1);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const { startDate, endDate } = computeRange(range, customRange);
  const { data: ranking, isLoading: isRankingLoading } = useCategoryRanking("expense", startDate, endDate);

  useEffect(() => {
    if (categoryId !== null) return;
    // Открываемся на самой крупной статье, а не на первой по алфавиту:
    // отчёт открывают с вопросом «куда уходят деньги», и первая буква
    // названия к нему отношения не имеет. Пока рейтинг не пришёл, ждём —
    // мигнуть чужой категорией и переключиться хуже, чем показать пусто.
    if (ranking && ranking.items.length > 0) {
      setCategoryId(ranking.items[0].category_id);
      return;
    }
    // Рейтинг пуст (нет трат за период) — берём хоть что-нибудь, иначе
    // страница остаётся без выбранной статьи навсегда.
    if (ranking && categories && categories.length > 0) {
      const firstExpense = categories.find((category) => category.kind === "expense");
      setCategoryId((firstExpense ?? categories[0]).id);
    }
  }, [categories, categoryId, ranking]);
  const { data: report, isLoading: isReportLoading } = useCategorySpendingReport(categoryId, startDate, endDate);
  const { data: transactions, isLoading: isTransactionsLoading } = useTransactions({
    category_id: categoryId ?? undefined,
    start_date: startDate,
    end_date: endDate,
    sort,
    page,
    page_size: PAGE_SIZE,
  });
  const deleteTransaction = useDeleteTransaction();
  const confirm = useConfirm();

  // Hierarchical within each group (a subcategory right under its own
  // parent, indented) — a bare "Sweets" option next to top-level categories
  // reads as if it were one itself.
  // Расходы и доходы одним списком с заголовками разделов: дерево
  // выстраивает сам выбиратель, ему нужен только вид для подписи.
  const filterCategories = (categories ?? [])
    .filter((category) => category.kind === "expense" || category.kind === "income")
    .map((category) => ({ ...category, group: t(category.kind === "expense" ? "reports.expenseGroup" : "reports.incomeGroup") }));
  const totalPages = transactions ? Math.max(1, Math.ceil(transactions.total / PAGE_SIZE)) : 1;

  function handleEdit(transaction: Transaction) {
    setEditingTransaction(transaction);
    setModalOpen(true);
  }

  async function handleDelete(transaction: Transaction) {
    const ok = await confirm({
      message: t("transactions.confirmDelete", { description: transaction.description ?? "—" }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (ok) deleteTransaction.mutate(transaction.id);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-xs flex-1">
          <Label htmlFor="report-category">{t("reports.categoryLabel")}</Label>
          <CategoryPicker
            id="report-category"
            categories={filterCategories}
            value={categoryId ? String(categoryId) : ""}
            onChange={(value) => {
              setCategoryId(Number(value));
              setPage(1);
            }}
            placeholder={t("reports.categoryLabel")}
          />
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <PillSelector
            options={RANGE_OPTIONS}
            value={range}
            onChange={(value) => {
              setRange(value);
              setPage(1);
            }}
          />
          {range === "custom" && (
            <DateRangeSelector
              years={years ?? [now.getFullYear()]}
              value={customRange}
              onChange={(value) => {
                setCustomRange(value);
                setPage(1);
              }}
            />
          )}
        </div>
      </div>

      <CategorySpendingChart report={report} isLoading={isReportLoading} />

      <CategoryRankingCard
        items={ranking?.items ?? []}
        isLoading={isRankingLoading}
        selectedCategoryId={categoryId}
        onSelectCategory={(id) => {
          setCategoryId(id);
          setPage(1);
        }}
      />

      <Card>
        <CardHeader>
          <CardTitle>{t("reports.transactionsTitle")}</CardTitle>
          {transactions && (
            <span className="text-xs text-text-muted">{t("common.totalCount", { count: transactions.total })}</span>
          )}
        </CardHeader>
        <CardContent>
          <Select
            value={sort}
            onChange={(event) => {
              setSort(event.target.value as TransactionSort);
              setPage(1);
            }}
            className="mb-3 sm:w-56"
          >
            <option value="date_desc">{t("transactions.sortDateDesc")}</option>
            <option value="amount_desc">{t("transactions.sortAmountDesc")}</option>
            <option value="amount_asc">{t("transactions.sortAmountAsc")}</option>
          </Select>
          {isTransactionsLoading ? (
            <p className="py-12 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <TransactionsTable items={transactions?.items ?? []} onEdit={handleEdit} onDelete={handleDelete} />
          )}

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-3 text-sm">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                {t("common.back")}
              </Button>
              <span className="text-text-muted">{t("common.pageOf", { page, total: totalPages })}</span>
              <Button variant="secondary" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                {t("common.next")}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <TransactionFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        transaction={editingTransaction}
      />
    </div>
  );
}
