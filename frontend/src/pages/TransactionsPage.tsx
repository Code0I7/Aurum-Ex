import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FileUp, Plus, Search, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { ColumnPicker } from "@/components/transactions/ColumnPicker";
import { TransactionsGrid } from "@/components/transactions/TransactionsGrid";
import { TransactionsTable } from "@/components/transactions/TransactionsTable";
import { DEFAULT_LAYOUT, reconcileLayout, type ColumnLayout } from "@/components/transactions/columns";
import { TransactionFormModal } from "@/components/transactions/TransactionFormModal";
import {
  useTransactions,
  useDeleteTransaction,
  useInfiniteTransactions,
  useReorderTransaction,
  useTransactionYears,
} from "@/hooks/useTransactions";
import { useCategories } from "@/hooks/useCategories";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
import { useTags } from "@/hooks/useTags";
import type { TransactionSort } from "@/api/transactions";
import { useTranslation } from "@/lib/i18n";
import { buildHierarchicalCategories, translateCategoryName } from "@/lib/categoryLabels";
import type { Transaction, TransactionType } from "@/types";

const PAGE_SIZE = 20;

/** Parses a query-param month, falling back to `fallback` for anything
 * missing or out of range (e.g. a hand-edited URL). Must check `value`
 * for null before `Number()` — `Number(null)` is 0, not NaN, so a missing
 * param would otherwise silently pass the integer check and clamp to 1. */
function parseMonthParam(value: string | null, fallback: number): number {
  if (value === null) return fallback;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 12 ? parsed : fallback;
}

function parseYearParam(value: string | null, fallback: number): number {
  if (value === null) return fallback;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

export function TransactionsPage() {
  const { t, language } = useTranslation();
  const now = new Date();
  // Deep-linked from the Dashboard's "All transactions" link, which carries
  // the month/year the user was already looking at (?year=&month=) so this
  // page doesn't reset back to the current month.
  const [searchParams] = useSearchParams();
  const [year, setYear] = useState(() => parseYearParam(searchParams.get("year"), now.getFullYear()));
  const [month, setMonth] = useState(() => parseMonthParam(searchParams.get("month"), now.getMonth() + 1));
  const [type, setType] = useState<TransactionType | "">("");
  const [categoryId, setCategoryId] = useState<string>("");
  const [tagId, setTagId] = useState<string>("");
  const [sort, setSort] = useState<TransactionSort>("date_desc");
  const [page, setPage] = useState(1);

  // Raw text follows every keystroke; the debounced value is what actually
  // drives the query, so we're not refetching on every character typed.
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const timeout = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timeout);
  }, [searchInput]);
  const isSearching = search.length > 0;

  // Вид и раскладка колонок переживают перезагрузку: человек настраивает их
  // под себя один раз, и возвращать таблицу к умолчанию на каждый заход
  // значило бы обесценить саму настройку.
  const [view, setView] = useLocalStorageState<"table" | "list">("aurum:transactions-view", "table");
  const [storedLayout, setStoredLayout] = useLocalStorageState<ColumnLayout>(
    "aurum:transactions-columns",
    DEFAULT_LAYOUT
  );
  // Склейка одинаковых операций одного дня: четыре поездки на автобусе
  // показываются одной строкой «Автобус ×4». Включена по умолчанию — именно
  // такие серии и забивают список, — но выключается одним нажатием.
  const [groupRepeats, setGroupRepeats] = useLocalStorageState<boolean>("aurum:transactions-group", true);
  // Постранично или лентой с кнопкой «Загрузить ещё». Страницы предсказуемы
  // и не растут в памяти — на четырёх годах истории это заметно; лента
  // удобнее, когда листаешь подряд. Верного ответа для всех случаев нет,
  // поэтому выбор оставлен человеку и запоминается.
  const [paging, setPaging] = useLocalStorageState<"pages" | "feed">("aurum:transactions-paging", "pages");
  // Сохранённая раскладка переживает обновления приложения, в которых
  // колонки появляются и исчезают, — сверяем её с текущим набором.
  const layout = reconcileLayout(storedLayout);

  const reorderTransaction = useReorderTransaction();

  /**
   * Переставляет операцию на визуальную позицию внутри её дня.
   *
   * Список идёт от нового к старому, а day_order растёт от раннего к
   * позднему — то есть визуальный порядок обратен хранимому. Перевод одной
   * формулой здесь: раньше кнопки двигали строку по day_order напрямую, и
   * на экране всё уезжало в противоположную сторону.
   */
  const handleReorder = (transaction: Transaction, visualIndex: number, countInDay: number) => {
    const position = Math.max(0, countInDay - 1 - visualIndex);
    if (position === transaction.day_order) return;
    reorderTransaction.mutate({ id: transaction.id, position });
  };

  const [modalOpen, setModalOpen] = useState(false);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);

  const { data: categories } = useCategories();
  const { data: tags } = useTags();
  const { data: years } = useTransactionYears();
  // Фильтры общие для обоих режимов; различается только то, как запрашиваются
  // страницы — по одной или с накоплением.
  const commonFilters = {
    // A search looks for a purchase from an unknown month, so it must span
    // every period instead of being boxed into the currently selected one.
    year: isSearching ? undefined : year,
    month: isSearching ? undefined : month,
    search: isSearching ? search : undefined,
    type: type || undefined,
    category_id: categoryId ? Number(categoryId) : undefined,
    tag_id: tagId ? Number(tagId) : undefined,
    sort,
    page_size: PAGE_SIZE,
  };

  const paged = useTransactions({ ...commonFilters, page }, paging === "pages");
  const feed = useInfiniteTransactions(commonFilters, paging === "feed");

  // Дальше страница работает с одной парой «строки и общее число», не
  // разбираясь, откуда они пришли.
  const items = paging === "pages" ? (paged.data?.items ?? []) : (feed.data?.pages.flatMap((p) => p.items) ?? []);
  const total = paging === "pages" ? (paged.data?.total ?? 0) : (feed.data?.pages[0]?.total ?? 0);
  const isLoading = paging === "pages" ? paged.isLoading : feed.isLoading;
  const isError = paging === "pages" ? paged.isError : feed.isError;

  const deleteTransaction = useDeleteTransaction();

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  // Grouped by kind and hierarchical within each group (a subcategory right
  // under its own parent, indented) — a bare "Sweets" option next to
  // top-level categories reads as if it were one itself.
  const expenseCategoryOptions = buildHierarchicalCategories(
    (categories ?? []).filter((category) => category.kind === "expense"),
    language
  );
  const incomeCategoryOptions = buildHierarchicalCategories(
    (categories ?? []).filter((category) => category.kind === "income"),
    language
  );

  function openCreateModal() {
    setEditingTransaction(null);
    setModalOpen(true);
  }

  function openEditModal(transaction: Transaction) {
    setEditingTransaction(transaction);
    setModalOpen(true);
  }

  function handleDelete(transaction: Transaction) {
    if (window.confirm(t("transactions.confirmDelete", { description: transaction.description }))) {
      deleteTransaction.mutate(transaction.id);
    }
  }

  /** Leaves search mode and switches the month/year selectors to whichever
   * month the picked transaction is in, so the user lands back in the normal
   * browsing view with it in context instead of a flat result list. */
  function handleJumpToMonth(transaction: Transaction) {
    const date = new Date(`${transaction.date}T00:00:00`);
    setYear(date.getFullYear());
    setMonth(date.getMonth() + 1);
    setSearchInput("");
    setSearch("");
    setPage(1);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className={`min-w-0 flex-1 ${isSearching ? "pointer-events-none opacity-50" : ""}`}>
            <MonthSelector
              month={month}
              onChange={(value) => {
                setMonth(value);
                setPage(1);
              }}
            />
          </div>
          <div className={isSearching ? "pointer-events-none opacity-50" : ""}>
            <YearSelector
              years={years ?? [now.getFullYear()]}
              year={year}
              onChange={(value) => {
                setYear(value);
                setPage(1);
              }}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* Перенос истории из таблицы — операция разовая, поэтому
              кнопка неброская и уходит в самый край. Обычный CSV-импорт
              банковской выписки рядом и остаётся основным. */}
          <Link to="/transactions/import-spreadsheet" className="flex-1 sm:flex-none">
            <Button variant="ghost" className="w-full sm:w-auto">
              <FileUp size={16} />
              {t("spreadsheet.buttonShort")}
            </Button>
          </Link>
          <Link to="/transactions/import" className="flex-1 sm:flex-none">
            <Button variant="secondary" className="w-full sm:w-auto">
              <FileUp size={16} />
              {t("transactions.importButton")}
            </Button>
          </Link>
          <Button onClick={openCreateModal} className="flex-1 sm:w-auto">
            <Plus size={16} />
            {t("transactions.addButton")}
          </Button>
        </div>
      </div>

      <div className="relative">
        <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <Input
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          placeholder={t("transactions.searchPlaceholder")}
          className="pl-9 pr-9"
        />
        {searchInput && (
          <button
            type="button"
            aria-label={t("common.clear")}
            onClick={() => {
              setSearchInput("");
              setSearch("");
              setPage(1);
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary"
          >
            <X size={15} />
          </button>
        )}
      </div>
      {isSearching && <p className="text-xs text-text-muted">{t("transactions.searchAcrossAllTime")}</p>}

      <div className="flex flex-col gap-3 sm:flex-row">
        <Select
          value={type}
          onChange={(event) => {
            setType(event.target.value as TransactionType | "");
            setPage(1);
          }}
          className="sm:w-48"
        >
          <option value="">{t("transactions.allTypes")}</option>
          <option value="expense">{t("transactions.expense")}</option>
          <option value="income">{t("transactions.income")}</option>
          <option value="transfer">{t("transactions.transfer")}</option>
        </Select>
        <Select
          value={categoryId}
          onChange={(event) => {
            setCategoryId(event.target.value);
            setPage(1);
          }}
          className="sm:w-56"
        >
          <option value="">{t("transactions.allCategories")}</option>
          {expenseCategoryOptions.length > 0 && (
            <optgroup label={t("reports.expenseGroup")}>
              {expenseCategoryOptions.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.indented ? `    ↳ ` : ""}
                  {translateCategoryName(category.name)}
                </option>
              ))}
            </optgroup>
          )}
          {incomeCategoryOptions.length > 0 && (
            <optgroup label={t("reports.incomeGroup")}>
              {incomeCategoryOptions.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.indented ? `    ↳ ` : ""}
                  {translateCategoryName(category.name)}
                </option>
              ))}
            </optgroup>
          )}
        </Select>
        {tags && tags.length > 0 && (
          <Select
            value={tagId}
            onChange={(event) => {
              setTagId(event.target.value);
              setPage(1);
            }}
            className="sm:w-48"
          >
            <option value="">{t("transactions.allTags")}</option>
            {tags.map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </Select>
        )}
        <Select
          value={sort}
          onChange={(event) => {
            setSort(event.target.value as TransactionSort);
            setPage(1);
          }}
          className="sm:w-56"
        >
          <option value="date_desc">{t("transactions.sortDateDesc")}</option>
          <option value="amount_desc">{t("transactions.sortAmountDesc")}</option>
          <option value="amount_asc">{t("transactions.sortAmountAsc")}</option>
        </Select>
      </div>

      <Card>
        {/* На узком экране заголовок и панель управления встают в две
            строки, а сами кнопки переносятся: в один ряд они не помещаются
            и вылезают за край карточки. */}
        <CardHeader className="flex-col items-stretch gap-3 sm:flex-row sm:items-center">
          <span className="flex items-baseline gap-2">
            <CardTitle>{t("nav.transactions")}</CardTitle>
            {total > 0 && (
              <span className="whitespace-nowrap text-xs text-text-muted">
                {t("common.totalCount", { count: total })}
              </span>
            )}
          </span>
          <span className="flex flex-wrap items-center gap-2 sm:justify-end">
            {!isSearching && (
              <>
                <Button variant="secondary" onClick={() => setView(view === "table" ? "list" : "table")}>
                  {view === "table" ? t("transactions.viewList") : t("transactions.viewTable")}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    // Возврат к страницам всегда начинается с первой: номер,
                    // на котором остановилась лента, ей не соответствует.
                    setPage(1);
                    setPaging(paging === "pages" ? "feed" : "pages");
                  }}
                >
                  {paging === "pages" ? t("transactions.pagingFeed") : t("transactions.pagingPages")}
                </Button>
                {view === "table" && (
                  <>
                    <Button
                      variant={groupRepeats ? "primary" : "secondary"}
                      onClick={() => setGroupRepeats(!groupRepeats)}
                      title={t("transactions.groupRepeatsHint")}
                      className="whitespace-nowrap"
                    >
                      {t("transactions.groupRepeats")}
                    </Button>
                    <ColumnPicker layout={layout} onChange={setStoredLayout} />
                  </>
                )}
              </>
            )}
          </span>
        </CardHeader>
        <CardContent>
          {isError && <p className="py-6 text-center text-sm text-danger">{t("transactions.failedToLoad")}</p>}
          {isLoading ? (
            <p className="py-12 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            view === "table" && !isSearching ? (
              <TransactionsGrid
                items={items}
                layout={layout}
                onEdit={openEditModal}
                onDelete={handleDelete}
                onReorder={handleReorder}
                groupRepeats={groupRepeats}
              />
            ) : (
              // При поиске остаётся список: результаты приходят из разных
              // месяцев, и колонка баланса в такой выборке смысла не имеет.
              <TransactionsTable
                items={items}
                onEdit={openEditModal}
                onDelete={handleDelete}
                onJumpToMonth={isSearching ? handleJumpToMonth : undefined}
              />
            )
          )}

          {paging === "pages" && totalPages > 1 && (
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

          {paging === "feed" && (
            <div className="mt-4 flex flex-col items-center gap-2 text-sm">
              {feed.hasNextPage ? (
                <Button
                  variant="secondary"
                  disabled={feed.isFetchingNextPage}
                  onClick={() => void feed.fetchNextPage()}
                >
                  {feed.isFetchingNextPage ? t("common.loading") : t("transactions.loadMore")}
                </Button>
              ) : (
                items.length > 0 && <span className="text-text-muted">{t("transactions.allLoaded")}</span>
              )}
              <span className="text-xs text-text-muted">
                {t("transactions.loadedCount", { loaded: items.length, total })}
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      <TransactionFormModal open={modalOpen} onClose={() => setModalOpen(false)} transaction={editingTransaction} />
    </div>
  );
}
