// Вид счёта. Переименовано из AccountType вместе с бэкендом; добавлен loan
// — рассрочка или кредит без пластика.
export type AccountKind =
  | "checking"
  | "savings"
  | "credit_card"
  | "cash"
  | "investment"
  | "crypto"
  | "loan"
  | "other";
// Актив или обязательство — отдельная ось от вида счёта.
export type AccountNature = "asset" | "liability";
export type ParticipantKind = "person" | "pet";
// Возвратность расчёта с внешним человеком: подарок долга не создаёт, заём
// создаёт. Ставится на операции, а не на контрагенте.
export type SettlementKind = "gift" | "loan_out" | "loan_in" | "repayment";
export type CategoryKind = "income" | "expense";
// external_in / external_out — деньги от другого человека и ему же: меняют
// баланс, но заработком не считаются.
export type TransactionType = "income" | "expense" | "transfer" | "external_in" | "external_out";
export type RecurringFrequency = "weekly" | "monthly" | "yearly";

export interface Bank {
  id: number;
  name: string;
  color: string | null;
  sort_order: number;
}

export interface Account {
  id: number;
  name: string;
  // Переименовано из type вместе с бэкендом: "тип" читался как "тип
  // записи" и путался с учётной записью.
  kind: AccountKind;
  // Актив или обязательство — отдельная ось от вида счёта: рассрочка ведёт
  // себя как кредитная карта, хотя по названию об этом ничего не сказано.
  nature: AccountNature;
  bank_id: number | null;
  bank: Bank | null;
  currency: string;
  // Деньги, лежавшие на счёте до первой записи. Часть баланса, но не доход.
  opening_balance: string;
  opening_date: string | null;
  allow_negative: boolean;
  color: string | null;
  is_archived: boolean;
}

// The Accounts management page's shape — /api/accounts' own endpoints add a
// live `balance` (summed from transactions) that a nested Transaction.account
// never carries. Keep the two separate rather than making `balance` optional
// on `Account`, so a stray `tx.account.balance` read is a compile error, not
// a silent `undefined` at runtime.
export interface AccountWithBalance extends Account {
  balance: string;
  // Отложено под цели и доступно к трате. Резерв НЕ уменьшает баланс:
  // деньги лежат там же, просто часть обещана другой задаче.
  reserved: string;
  available: string;
}

export interface AccountInput {
  name: string;
  kind: AccountKind;
}

export interface Category {
  id: number;
  name: string;
  kind: CategoryKind;
  icon: string | null;
  color: string;
  sort_order: number;
  is_default: boolean;
  // Subcategory parent, one level deep only (a category whose own parent_id
  // is set can't itself have children — enforced backend-side).
  parent_id: number | null;
}

export interface CategoryInput {
  name: string;
  kind: CategoryKind;
  icon?: string | null;
  color: string;
  sort_order?: number;
  parent_id?: number | null;
}

// kind is fixed at creation on the backend (CategoryUpdate has no kind field).
export interface CategoryUpdateInput {
  name?: string;
  icon?: string | null;
  color?: string;
  sort_order?: number;
  parent_id?: number | null;
}

export interface Tag {
  id: number;
  name: string;
}

// One category's slice of a transaction whose amount is divided across
// several categories (one receipt, several kinds of goods) — see
// TransactionInput.splits. category is null when the split's category was
// since deleted; reading must still work even though creating/editing a
// split always requires a live category.
export interface TransactionSplit {
  id: number;
  category_id: number | null;
  category: Category | null;
  amount: string;
  note: string | null;
}

export interface TransactionSplitInput {
  category_id: number;
  amount: string;
  note?: string | null;
}

export interface Participant {
  id: number;
  name: string;
  kind: ParticipantKind;
  color: string | null;
  is_archived: boolean;
}

export interface Store {
  id: number;
  name: string;
  location: string | null;
  notes: string | null;
  is_archived: boolean;
}

export interface Counterparty {
  id: number;
  name: string;
  notes: string | null;
  is_archived: boolean;
}

export interface Transaction {
  id: number;
  uuid: string;
  account_id: number;
  category_id: number | null;
  transfer_account_id: number | null;
  type: TransactionType;
  amount: string;
  // Валюта операции и её сумма в базовой валюте по курсу на дату операции.
  // Курс заморожен в записи: пересчёт по сегодняшнему курсу переписывал бы
  // прошлое.
  currency: string;
  description: string;
  merchant: string | null;
  notes: string | null;
  date: string;
  // Порядок внутри дня. Без него операции одного дня раскладываются
  // произвольно и баланс проваливается там, где этого не было.
  day_order: number;
  // Запись видна в истории, но в суммы и графики не входит.
  is_excluded: boolean;
  participant_id: number | null;
  store_id: number | null;
  counterparty_id: number | null;
  settlement_kind: SettlementKind | null;
  account: Account;
  category: Category | null;
  tags: Tag[];
  splits: TransactionSplit[];
  // Баланс счёта после этой операции. Приходит только в списке — у ответа
  // на создание или правку остаётся null.
  balance_after: string | null;
}

export interface TransactionPage {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface TransactionInput {
  account_id: number;
  category_id: number | null;
  transfer_account_id: number | null;
  type: TransactionType;
  amount: string;
  description: string;
  merchant?: string | null;
  notes?: string | null;
  date: string;
  // Omitted -> tags untouched on update; sent (even as []) -> replaces the
  // full tag set. Always sent on create (defaults to []).
  tag_ids?: number[];
  // Omitted -> a normal single-category transaction (unchanged). 2+ entries
  // -> the amount is divided across categories instead, and category_id
  // above must then be null. On update, omitted leaves existing splits
  // untouched; sent (even as []) replaces the full split set.
  splits?: TransactionSplitInput[] | null;
}

export interface RecurringTransaction {
  id: number;
  account_id: number;
  account_name: string;
  category_id: number | null;
  category_name: string | null;
  category_color: string | null;
  category_icon: string | null;
  transfer_account_id: number | null;
  transfer_account_name: string | null;
  type: TransactionType;
  amount: string;
  description: string;
  merchant: string | null;
  notes: string | null;
  frequency: RecurringFrequency;
  anchor_date: string;
  last_posted_date: string | null;
  is_active: boolean;
  next_due_date: string;
  is_due: boolean;
  days_until_due: number;
}

export interface RecurringTransactionInput {
  account_id: number;
  category_id: number | null;
  transfer_account_id: number | null;
  type: TransactionType;
  amount: string;
  description: string;
  merchant?: string | null;
  frequency: RecurringFrequency;
  anchor_date: string;
}

// One subcategory's (or the parent's own direct, un-subcategorized) share
// of a CategoryBreakdownItem's total. Populated only when more than one
// distinct category fed the slice — a single-source category (the common
// case) leaves this off the parent item entirely.
export interface CategoryBreakdownChildItem {
  category_id: number;
  name: string;
  color: string;
  icon: string | null;
  amount: string;
}

export interface CategoryBreakdownItem {
  category_id: number | null;
  name: string;
  color: string;
  icon: string | null;
  amount: string;
  percent: number;
  children: CategoryBreakdownChildItem[];
}

export interface DashboardSummary {
  year: number;
  month: number;
  real_income: string;
  spent: string;
  net: string;
  transferred_out: string;
  spending_by_category: CategoryBreakdownItem[];
}

export type AssetClass = "investments" | "crypto" | "real_estate" | "vehicles" | "precious_metals" | "other";
export type NetWorthRange = "30d" | "90d" | "1y" | "5y" | "all";
export type CapitalRole = "income" | "neutral" | "drain";
export type RiskLevel = "low" | "medium" | "high";

export interface Asset {
  id: number;
  name: string;
  asset_class: AssetClass;
  currency: string;
  notes: string | null;
  capital_role: CapitalRole;
  monthly_cash_flow: string | null;
  risk_level: RiskLevel;
  current_value: string;
  as_of_date: string;
}

export interface AssetInput {
  name: string;
  asset_class: AssetClass;
  currency?: string;
  notes?: string | null;
  capital_role?: CapitalRole;
  monthly_cash_flow?: string | null;
  risk_level?: RiskLevel;
  value: string;
  as_of_date: string;
}

export interface AssetUpdateInput {
  name?: string;
  asset_class?: AssetClass;
  notes?: string | null;
  capital_role?: CapitalRole;
  monthly_cash_flow?: string | null;
  risk_level?: RiskLevel;
}

export interface AssetValuationInput {
  value: string;
  as_of_date: string;
}

export interface NetWorthPoint {
  date: string;
  value: string;
}

export interface NetWorthBreakdownItem {
  key: string;
  name: string;
  color: string;
  icon: string;
  amount: string;
  percent: number;
}

export interface CapitalRoleSummary {
  role: CapitalRole;
  label: string;
  color: string;
  total_value: string;
  monthly_cash_flow: string;
  count: number;
}

export interface RiskLevelItem {
  key: string;
  name: string;
  amount: string;
  percent: number;
}

export interface RiskLevelSummary {
  risk_level: RiskLevel;
  label: string;
  color: string;
  total_value: string;
  percent: number;
  items: RiskLevelItem[];
}

export interface NetWorthSummary {
  range: NetWorthRange;
  current: string;
  change_amount: string;
  change_percent: number | null;
  series: NetWorthPoint[];
  breakdown: NetWorthBreakdownItem[];
  capital_roles: CapitalRoleSummary[];
  risk_levels: RiskLevelSummary[];
}

export interface CategorySpendingPoint {
  year: number;
  month: number;
  amount: string;
}

export interface CategorySpendingReport {
  category_id: number;
  category_name: string;
  category_color: string;
  category_icon: string | null;
  start_date: string | null;
  end_date: string | null;
  total_amount: string;
  transaction_count: number;
  average_per_month: string;
  series: CategorySpendingPoint[];
}

export interface CashFlowPoint {
  year: number;
  month: number;
  income: string;
  expense: string;
  net: string;
  // Начальный остаток счетов, открытых в этом месяце. Уже входит в income
  // (или в expense, если отрицателен).
  opening: string;
}

export interface CashFlowResponse {
  start_date: string | null;
  end_date: string | null;
  points: CashFlowPoint[];
  total_income: string;
  total_expense: string;
  total_net: string;
  total_opening: string;
}

export interface CategoryRankingChildItem {
  category_id: number;
  name: string;
  color: string;
  icon: string | null;
  amount: string;
}

export interface CategoryRankingItem {
  category_id: number;
  name: string;
  color: string;
  icon: string | null;
  amount: string;
  percent: number;
  transaction_count: number;
  children: CategoryRankingChildItem[];
}

export interface CategoryRankingReport {
  start_date: string | null;
  end_date: string | null;
  total_amount: string;
  items: CategoryRankingItem[];
}

export interface Goal {
  id: number;
  name: string;
  target_amount: string;
  target_date: string | null;
  // Счёт, на котором физически лежат отложенные деньги. Без него счёт не
  // сможет показать «отложено»: непонятно, откуда цель копит.
  account_id: number | null;
  current_amount: string;
  remaining: string;
  percent: number;
  is_reached: boolean;
}

export interface GoalInput {
  name: string;
  target_amount: string;
  target_date: string | null;
  account_id: number | null;
}

// Расчёты с людьми. Оборот и долг — разные величины: жена, передавшая за
// четыре года полмиллиона на продукты, ничего не должна.
export interface Settlement {
  counterparty_id: number;
  name: string;
  received: string;
  given: string;
  owed_to_me: string;
  owed_by_me: string;
  // Плюс — должны вам, минус — должны вы.
  balance: string;
  operations: number;
  last_date: string | null;
}

export interface SettlementSummary {
  owed_to_me: string;
  owed_by_me: string;
}

// Условия по кредиту. Сам долг описан счётом — отрицательным балансом;
// здесь то, чего в таблице не было: во сколько этот долг обходится.
export interface CreditTerms {
  account_id: number;
  account_name: string;
  // Долг положительным числом — читается легче, чем «баланс −12 300».
  debt: string;
  annual_rate_percent: string | null;
  credit_limit: string | null;
  available: string | null;
  used_percent: number | null;
  grace_days: number | null;
  payment_day: number | null;
  minimum_payment: string | null;
  // Оценка, а не банковское число: льготный период здесь не воспроизводится.
  estimated_monthly_interest: string | null;
  opened_on: string | null;
  closes_on: string | null;
  notes: string | null;
}

export interface CreditTermsInput {
  annual_rate_percent?: string | null;
  credit_limit?: string | null;
  grace_days?: number | null;
  payment_day?: number | null;
  minimum_payment?: string | null;
  opened_on?: string | null;
  closes_on?: string | null;
  notes?: string | null;
}

export interface CreditSummary {
  debt: string;
  estimated_monthly_interest: string;
}

export interface GoalContributionInput {
  amount: string;
  date: string;
  note?: string | null;
}

export interface Budget {
  id: number;
  category_id: number;
  category_name: string;
  category_color: string;
  category_icon: string | null;
  monthly_limit: string;
}

export interface BudgetInput {
  category_id: number;
  monthly_limit: string;
}

export interface BudgetStatus {
  budget_id: number;
  category_id: number;
  category_name: string;
  category_color: string;
  category_icon: string | null;
  monthly_limit: string;
  spent: string;
  remaining: string;
  percent: number;
  is_over_budget: boolean;
}

export interface BudgetStatusResponse {
  year: number;
  month: number;
  items: BudgetStatus[];
}

export interface AdviceItem {
  key: string;
  tone: "positive" | "neutral" | "warning";
  params: Record<string, string | number>;
}

export interface AdviceResponse {
  items: AdviceItem[];
}

export interface FinancialAlert {
  key: string;
  severity: string;
  params: Record<string, number>;
}

export type CryptoTransactionType = "buy" | "sell";

export interface CryptoPortfolio {
  id: number;
  name: string;
  color: string | null;
  is_archived: boolean;
}

export interface CryptoPortfolioInput {
  name: string;
  is_archived?: boolean;
}

export interface CryptoHolding {
  asset_id: number;
  portfolio_id: number;
  coingecko_id: string;
  symbol: string;
  name: string;
  thumb_url: string | null;
  // Both derived from the buy/sell log (see CryptoTransaction) — never
  // edited directly.
  quantity: string;
  avg_buy_price: string | null;
  // Cached from the last successful CoinGecko sync — null means "added but
  // never priced yet" (CoinGecko was unreachable right at creation),
  // distinct from a real zero.
  current_price: string | null;
  price_change_1h: string | null;
  price_change_24h: string | null;
  price_change_7d: string | null;
  price_change_30d: string | null;
  // Stands in for "all time" on the Best/Worst Performer stat — CoinGecko's
  // free tier caps historical lookback at 365 days regardless.
  price_change_1y: string | null;
  value: string | null;
  cost_basis: string | null;
  profit_loss: string | null;
  profit_loss_percent: number | null;
}

export interface CryptoHoldingCreateInput {
  // Omit to file the coin under the default portfolio (auto-created if
  // none exists yet — see services/crypto_service.py's
  // get_or_create_default_portfolio).
  portfolio_id?: number | null;
  coingecko_id: string;
  symbol: string;
  name: string;
  thumb_url?: string | null;
  // A holding always starts with its first buy.
  quantity: string;
  price_per_unit: string;
  date: string;
  note?: string | null;
}

export interface CryptoTransaction {
  id: number;
  asset_id: number;
  type: CryptoTransactionType;
  quantity: string;
  price_per_unit: string;
  date: string;
  note: string | null;
}

export interface CryptoTransactionInput {
  type: CryptoTransactionType;
  quantity: string;
  price_per_unit: string;
  date: string;
  note?: string | null;
}

export interface CryptoSyncResult {
  synced: boolean;
  last_synced_at: string | null;
  error_key: "unreachable" | null;
  holdings: CryptoHolding[];
}

export interface CryptoSearchResult {
  coingecko_id: string;
  symbol: string;
  name: string;
  thumb_url: string | null;
}

// Real 90-day % price change per coin, fetched on demand only while the
// 90d range is selected — see services/crypto_service.py's
// get_90d_performance for why this can't ride along with the regular sync.
export interface CryptoPerformancePoint {
  asset_id: number;
  price_change_percent: number | null;
}

export interface CryptoPerformanceResponse {
  items: CryptoPerformancePoint[];
}

// No "24h" — the price history is only as dense as the sync cadence (see
// services/crypto_service.py's AUTO_REFRESH_INTERVAL), so a 24h chart would
// be one or two points, not a smooth intraday line.
export type CryptoRange = "7d" | "30d" | "90d" | "all";

export interface CryptoHistoryPoint {
  date: string;
  value: string;
}

export interface CryptoHistoryResponse {
  range: CryptoRange;
  current: string;
  change_amount: string;
  change_percent: number | null;
  series: CryptoHistoryPoint[];
}

export interface AppSettings {
  currency: string;
  negative_cash_flow_threshold_months: number;
  net_worth_decline_threshold_months: number;
  risky_allocation_threshold_percent: number;
  idle_cash_threshold_amount: string;
  idle_cash_threshold_days: number;
}

export interface HealthStatus {
  status: string;
  version: string;
}


// Планирование. Отличается от бюджета: бюджет — потолок на месяц, который
// предупреждает; план — ожидание на годы, из которого складывается картина
// года.
export type PlanKind = "one_off" | "monthly" | "daily";

export interface Plan {
  id: number;
  category_id: number | null;
  category_name: string | null;
  participant_id: number | null;
  kind: PlanKind;
  // Для разового и ежемесячного — сумма на месяц, для ежедневного — на день.
  amount: string;
  currency: string;
  valid_from: string;
  valid_to: string | null;
  // Только для ежедневного: считать по отработанным дням, а не календарным.
  workdays_only: boolean;
  note: string | null;
  is_active: boolean;
}

export interface PlanInput {
  category_id: number | null;
  kind: PlanKind;
  amount: string;
  valid_from: string;
  valid_to: string | null;
  workdays_only: boolean;
  note: string | null;
}

export interface PlanMonthCell {
  month: number;
  planned: string;
  actual: string;
  // Факт минус план. Что считать хорошим знаком, решает вид строки.
  deviation: string;
}

export interface PlanRow {
  category_id: number | null;
  name: string;
  kind: CategoryKind;
  months: PlanMonthCell[];
  planned_total: string;
  actual_total: string;
}

export interface PlanOverview {
  year: number;
  rows: PlanRow[];
  income_totals: PlanMonthCell[];
  expense_totals: PlanMonthCell[];
  // Свободные средства: доходы минус расходы, по плану и по факту.
  free_totals: PlanMonthCell[];
}

export interface WorkPeriod {
  id: number;
  year: number;
  month: number;
  hours: string;
  workdays: number | null;
  participant_id: number | null;
}

export interface WorkPeriodInput {
  year: number;
  month: number;
  hours: string;
  workdays: number | null;
}
