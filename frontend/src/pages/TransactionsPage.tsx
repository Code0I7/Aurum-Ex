import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus, Search, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { PageActions } from "@/components/layout/PageActions";
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
import { useAccounts } from "@/hooks/useAccounts";
import { useCounterparties } from "@/hooks/useDirectories";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
import { useSessionState } from "@/hooks/useSessionState";
import { useViewDefault } from "@/hooks/useViewDefault";
import { useAppSettings } from "@/hooks/useSettings";
import { useTags } from "@/hooks/useTags";
import type { TransactionSort } from "@/api/transactions";
import { useTranslation } from "@/lib/i18n";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { CategoryPicker } from "@/components/categories/CategoryPicker";
import type { Transaction, TransactionType } from "@/types";



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
  const { t } = useTranslation();
  const now = new Date();
  // Deep-linked from the Dashboard's "All transactions" link, which carries
  // the month/year the user was already looking at (?year=&month=) so this
  // page doesn't reset back to the current month.
  const [searchParams] = useSearchParams();
  const { data: settings } = useAppSettings();
  const { data: accounts } = useAccounts(false);
  // Сколько подгружать за раз — настройка, а не константа. Список и так
  // ограничен выбранным месяцем, который переключается кнопками, но
  // месяцы разной плотности: две с половиной тысячи операций за четыре
  // года — это под полсотни в месяц, и на двадцати строках обычный месяц
  // разваливается на три страницы. В поиске, который идёт по всей
  // истории, тем более.
  const pageSize = settings?.default_page_size ?? 50;
  // Месяц, фильтры и страница держатся до конца сеанса: уход в отчёты и
  // возвращение обратно не должны сбрасывать человека на текущий месяц.
  // Именно «до конца сеанса», а не навсегда: открывать приложение завтра
  // на прошлогоднем августе — не память, а ловушка.
  const [year, setYear] = useSessionState(
    "aurum:tx-year",
    parseYearParam(searchParams.get("year"), now.getFullYear())
  );
  const [month, setMonth] = useSessionState(
    "aurum:tx-month",
    parseMonthParam(searchParams.get("month"), now.getMonth() + 1)
  );
  // Насколько широко смотрим. Месяц — обычный режим ведения учёта, но
  // выписка по счёту за один август ни о чём не говорит: путаницу между
  // парой связанных счетов видно только на всей истории. Запоминается,
  // потому что человек, разбирающийся с переводами, делает это не за один
  // заход.
  const [scope, setScope] = useLocalStorageState<"month" | "year" | "all">(
    "aurum:transactions-scope",
    "month"
  );
  const [type, setType] = useSessionState<TransactionType | "">("aurum:tx-type", "");
  // Человек, с которым шёл расчёт. Спрашивают о нём тогда же, когда о долге:
  // «сколько я ему передал» — вопрос к списку операций, а не к сводке, и
  // искать их глазами по месяцам занимает больше времени, чем сам разговор.
  const [counterpartyId, setCounterpartyId] = useSessionState<string>("aurum:tx-counterparty", "");
  const [categoryId, setCategoryId] = useSessionState<string>("aurum:tx-category", "");
  // Выписка по одному счёту. Без неё распутать пару счетов вроде «карта и
  // рассрочка того же магазина» невозможно: движения между ними видно
  // только вперемешку со всем остальным.
  const [accountId, setAccountId] = useSessionState<string>("aurum:tx-account", "");
  const [tagId, setTagId] = useSessionState<string>("aurum:tx-tag", "");
  const [sort, setSort] = useSessionState<TransactionSort>("aurum:tx-sort", "date_desc");
  const [page, setPage] = useSessionState("aurum:tx-page", 1);

  // Переход по ссылке с дашборда несёт месяц в адресе — значит спрашивают
  // именно про него, и сохранённый широкий период на этот раз уступает.
  const deepLinkedMonth = searchParams.get("month") !== null;
  useEffect(() => {
    if (deepLinkedMonth) setScope("month");
    // Один раз при заходе: дальше период переключает человек.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
  const [groupRepeats, setGroupRepeats] = useViewDefault(
    "aurum:transactions-group",
    settings?.group_repeats_by_default,
    true,
  );
  // Постранично или лентой с кнопкой «Загрузить ещё». Страницы предсказуемы
  // и не растут в памяти — на четырёх годах истории это заметно; лента
  // удобнее, когда листаешь подряд. Верного ответа для всех случаев нет,
  // поэтому выбор оставлен человеку и запоминается.
  const [paging, setPaging] = useLocalStorageState<"pages" | "feed">("aurum:transactions-paging", "pages");
  // Разделители дней с итогами. Включены по умолчанию — так список читается
  // как банковская выписка, — но кому-то нужен сплошной перечень.
  const [dayDividers, setDayDividers] = useViewDefault(
    "aurum:transactions-day-dividers",
    settings?.day_dividers_by_default,
    true,
  );
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
  // Идентификаторы приходят уже в порядке дня, а место — тоже в нём:
  // перевод из показанного порядка в хранимый делает сама таблица, потому
  // что только она знает, из чего состоит строка (одна операция или
  // свёрнутая группа) и что стоит ниже неё.
  const handleReorder = (ids: number[], position: number) => {
    reorderTransaction.mutate({ ids, position });
  };

  const [modalOpen, setModalOpen] = useState(false);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);

  const { data: categories } = useCategories();
  const { data: tags } = useTags();
  const { data: counterparties } = useCounterparties();
  const { data: years } = useTransactionYears();
  // Человека спрашивают только у расчётов: у покупки в магазине контрагента
  // нет, и пустой список там обещал бы отбор, которого не существует.
  const showPartyFilter = type === "external_out" || type === "external_in";
  // Фильтры общие для обоих режимов; различается только то, как запрашиваются
  // страницы — по одной или с накоплением.
  const commonFilters = {
    // A search looks for a purchase from an unknown month, so it must span
    // every period instead of being boxed into the currently selected one.
    // Поиск идёт по всей истории независимо от выбранного периода: ищут
    // покупку, о которой не помнят, в каком она была месяце.
    year: isSearching || scope === "all" ? undefined : year,
    month: isSearching || scope !== "month" ? undefined : month,
    search: isSearching ? search : undefined,
    type: type || undefined,
    // Только когда поле видно. Фильтр, который не показан, но продолжает
    // сужать список, читается как поломанный период: строк мало, а почему —
    // не видно нигде.
    counterparty_id: showPartyFilter && counterpartyId ? Number(counterpartyId) : undefined,
    category_id: categoryId ? Number(categoryId) : undefined,
    account_id: accountId ? Number(accountId) : undefined,
    tag_id: tagId ? Number(tagId) : undefined,
    sort,
    page_size: pageSize,
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
  const confirm = useConfirm();

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const scopes: Array<{ key: "month" | "year" | "all"; label: string }> = [
    { key: "month", label: t("dashboard.rangeMonth") },
    { key: "year", label: t("dashboard.rangeYear") },
    { key: "all", label: t("dashboard.rangeAll") },
  ];
  // Grouped by kind and hierarchical within each group (a subcategory right
  // under its own parent, indented) — a bare "Sweets" option next to
  // top-level categories reads as if it were one itself.
  const filterCategories = (categories ?? [])
    .filter((category) => category.kind === "expense" || category.kind === "income")
    .map((category) => ({
      ...category,
      group: t(category.kind === "expense" ? "reports.expenseGroup" : "reports.incomeGroup"),
    }));

  function openCreateModal() {
    setEditingTransaction(null);
    setModalOpen(true);
  }

  function openEditModal(transaction: Transaction) {
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

  /** Leaves search mode and switches the month/year selectors to whichever
   * month the picked transaction is in, so the user lands back in the normal
   * browsing view with it in context instead of a flat result list. */
  function handleJumpToMonth(transaction: Transaction) {
    const date = new Date(`${transaction.date}T00:00:00`);
    setYear(date.getFullYear());
    setMonth(date.getMonth() + 1);
    // И период сужается до месяца: иначе «показать в контексте» вернуло бы
    // ту же ленту за всё время, из которой человек только что пришёл.
    setScope("month");
    setSearchInput("");
    setSearch("");
    setPage(1);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className={`min-w-0 flex-1 space-y-3 ${isSearching ? "pointer-events-none opacity-50" : ""}`}>
          {/* Выбор года стоит здесь, рядом с выбором периода, а не сбоку от
              полосы месяцев. Раньше он висел справа от месяцев и при
              переключении на «год» перескакивал влево: одна и та же кнопка
              оказывалась то посреди строки, то у края. */}
          <div className="flex items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-1">
              {scopes.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => {
                  setScope(item.key);
                  setPage(1);
                }}
                className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                  scope === item.key
                    ? "bg-surface-2 text-text-primary"
                    : "text-text-muted hover:bg-surface-2 hover:text-text-primary"
                }`}
              >
                  {item.label}
                </button>
              ))}
            </div>
            {scope !== "all" && (
              <YearSelector
                years={years ?? [now.getFullYear()]}
                year={year}
                onChange={(value) => {
                  setYear(value);
                  setPage(1);
                }}
              />
            )}
          </div>
          {/* Полоса месяцев прячется, когда она ни на что не влияет:
              переключатель, который ничего не меняет, — обещание, которого
              приложение не выполняет. Год при этом остаётся на месте выше. */}
          {scope === "month" && (
            <MonthSelector
              month={month}
              onChange={(value) => {
                setMonth(value);
                setPage(1);
              }}
            />
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {/* Импорта здесь больше нет — обе кнопки переехали в настройки.
              Рядом они выглядели как одно и то же, сделанное дважды, хотя
              одна переносит таблицу целиком на пустую установку, а вторая
              дополняет накопленное выпиской за месяц. Для вкладки, где
              операции заводят каждый день, обе разовые. */}
          <PageActions>
            <Button onClick={openCreateModal}>
              <Plus size={16} />
              {t("transactions.addButton")}
            </Button>
          </PageActions>
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
            // Уходя с расчётов, снимаем и человека: иначе он остался бы
            // висеть в сессии и сузил бы следующий отбор молча.
            setCounterpartyId("");
            setPage(1);
          }}
          className="sm:w-48"
        >
          <option value="">{t("transactions.allTypes")}</option>
          <option value="expense">{t("transactions.expense")}</option>
          <option value="income">{t("transactions.income")}</option>
          <option value="transfer">{t("transactions.transfer")}</option>
          {/* Расчёты с людьми были в форме, но не в фильтре: найти их можно
              было только глазами по списку. Подписи те же, что в форме, —
              человек ищет то, что сам туда и записал. */}
          <option value="external_out">{t("transactions.form.typeExternalOut")}</option>
          <option value="external_in">{t("transactions.form.typeExternalIn")}</option>
        </Select>
        {/* Человек — сразу за видом операции: он уточняет именно его, и
            между ними не должно стоять ничего постороннего. */}
        {showPartyFilter && (
          <Select
            value={counterpartyId}
            onChange={(event) => {
              setCounterpartyId(event.target.value);
              setPage(1);
            }}
            className="sm:w-44"
          >
            <option value="">{t("transactions.allCounterparties")}</option>
            {(counterparties ?? []).map((counterparty) => (
              <option key={counterparty.id} value={counterparty.id}>
                {counterparty.name}
              </option>
            ))}
          </Select>
        )}
        <Select
          value={accountId}
          onChange={(event) => {
            setAccountId(event.target.value);
            setPage(1);
          }}
          className="sm:w-44"
        >
          <option value="">{t("transactions.allAccounts")}</option>
          {(accounts ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>
        <CategoryPicker
          categories={filterCategories}
          value={categoryId}
          onChange={(value) => {
            setCategoryId(value);
            setPage(1);
          }}
          className="sm:w-56"
          placeholder={t("transactions.allCategories")}
          emptyLabel={t("transactions.allCategories")}
        />
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
                    <Button
                      variant={dayDividers ? "primary" : "secondary"}
                      onClick={() => setDayDividers(!dayDividers)}
                      title={t("transactions.dayDividersHint")}
                      className="whitespace-nowrap"
                    >
                      {t("transactions.dayDividers")}
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
                dayDividers={dayDividers}
                chronological={sort === "date_desc"}
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
