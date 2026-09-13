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
export type SettlementKind = "gift" | "loan_out" | "loan_in" | "repayment" | "transit";
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
  // Тот же остаток в валюте установки, по сегодняшнему курсу. У счёта в
  // своей валюте совпадает с balance — так читающему не нужна отдельная
  // ветка на «а вдруг валюта та же».
  balance_base: string;
  // Отложено под цели и доступно к трате. Резерв НЕ уменьшает баланс:
  // деньги лежат там же, просто часть обещана другой задаче.
  reserved: string;
  available: string;
  // Сколько операций записано на счёт. Нужно форме: при смене валюты она
  // говорит, сколько записей будет пересчитано.
  transaction_count: number;
}

export interface AccountInput {
  name: string;
  kind: AccountKind;
  // Валюта счёта. Меняется и потом: операции счёта переходят в новую
  // валюту вместе с ним, а пересчёт в валюту установки выполняется заново
  // по курсам на их даты.
  currency: string;
}

export interface Category {
  id: number;
  name: string;
  kind: CategoryKind;
  icon: string | null;
  color: string;
  sort_order: number;
  is_default: boolean;
  // Родитель. Вложенность произвольной глубины: ограничение в один уровень
  // снято, границы ставит бэкенд (циклы, вид, предел глубины).
  parent_id: number | null;
  // В списке наблюдения на вкладке планирования.
  is_watched: boolean;
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
  // Применить цвет и значок ко всей ветке под категорией.
  apply_style_to_children?: boolean;
  is_watched?: boolean;
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
  // Сколько операций ссылается на запись: удаление не должно быть
  // вслепую.
  usage: number;
  id: number;
  name: string;
  kind: ParticipantKind;
  color: string | null;
  is_archived: boolean;
}

export interface Store {
  // Сколько операций ссылается на запись: удаление не должно быть
  // вслепую.
  usage: number;
  // Сколько денег ушло в магазин: за всё время и за скользящий год.
  // Число покупок само по себе обманывает — сорок заходов в булочную
  // выглядят весомее четырёх заказов на маркетплейсе.
  spent_total: string;
  spent_year: string;
  id: number;
  name: string;
  location: string | null;
  // Полка на странице справочников: ни в отчёты, ни в подстановку не идёт.
  group_name: string | null;
  notes: string | null;
  is_archived: boolean;
}

export interface Counterparty {
  // Сколько операций ссылается на запись: удаление не должно быть
  // вслепую.
  usage: number;
  id: number;
  name: string;
  // Полка на странице справочников: ни в отчёты, ни в подстановку не идёт.
  group_name: string | null;
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
  // Валюта операции и её сумма в валюте установки по курсу на дату
  // операции. Курс заморожен в записи: пересчёт по сегодняшнему переписывал
  // бы прошлое.
  currency: string;
  // Пусто, когда курса на дату операции нет: в списке у такой строки
  // пометка, а в итоги она не входит. Молчаливая единица на её месте
  // выглядела бы обычным числом.
  amount_base: string | null;
  /**
   * Вторая сторона перевода между разными валютами: сколько пришло на счёт
   * получателя, в его валюте, и сколько это в валюте установки. Пусто у
   * обычного перевода — там пришло ровно столько же, сколько ушло, и
   * второе число было бы копией первого.
   */
  transfer_amount: string | null;
  transfer_currency: string | null;
  /** Кто и сколько внёс, когда операция разделена между людьми. Пусто у
   *  обычной: там контрагент один и назван полем. */
  counterparty_splits: TransactionCounterpartySplit[];
  transfer_amount_base: string | null;
  // Необязательно: у большинства покупок сказать сверх категории нечего.
  description: string | null;
  merchant: string | null;
  date: string;
  // Порядок внутри дня. Без него операции одного дня раскладываются
  // произвольно и баланс проваливается там, где этого не было.
  day_order: number;
  // Запись видна в истории, но в суммы и графики не входит.
  is_excluded: boolean;
  participant_id: number | null;
  store_id: number | null;
  counterparty_id: number | null;
  // Вторая сторона транзита: у прихода «для кого», у расхода «чьи деньги».
  transit_party_id: number | null;
  settlement_kind: SettlementKind | null;
  account: Account;
  category: Category | null;
  tags: Tag[];
  splits: TransactionSplit[];
  // Состав чека. Пустой список — совершенно нормальная операция: быстрый
  // ввод остаётся одним действием.
  items: TransactionItem[];
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

/** Доля одного человека в операции, разделённой между несколькими. */
export interface TransactionCounterpartySplit {
  id: number;
  counterparty_id: number | null;
  counterparty: Counterparty | null;
  amount: string;
  note: string | null;
}

export interface TransactionCounterpartySplitInput {
  counterparty_id: number;
  amount: string;
  note?: string | null;
}

export interface TransactionInput {
  account_id: number;
  /** Сколько пришло на счёт получателя, в его валюте. Обязательно для
   *  перевода между разными валютами, не нужно во всех остальных случаях. */
  transfer_amount?: string | null;
  /**
   * Разбивка между людьми: долг вернули трое одним переводом.
   *
   * Заменяет counterparty_id, а не дополняет его — два ответа на «от кого»
   * означали бы, что операция посчитана дважды. Пропущено — разбивка не
   * трогается; список (в том числе пустой) заменяет её целиком.
   */
  counterparty_splits?: TransactionCounterpartySplitInput[] | null;
  category_id: number | null;
  transfer_account_id: number | null;
  type: TransactionType;
  amount: string;
  description?: string | null;
  merchant?: string | null;
  date: string;
  // Omitted -> tags untouched on update; sent (even as []) -> replaces the
  // full tag set. Always sent on create (defaults to []).
  tag_ids?: number[];
  // Omitted -> a normal single-category transaction (unchanged). 2+ entries
  // -> the amount is divided across categories instead, and category_id
  // above must then be null. On update, omitted leaves existing splits
  // untouched; sent (even as []) replaces the full split set.
  splits?: TransactionSplitInput[] | null;
  // При правке: список (включая пустой) заменяет состав целиком, отсутствие
  // поля оставляет как было.
  items?: TransactionItemInput[] | null;
  // Кто, где и с кем. Все необязательны: быстрый ввод не должен требовать
  // заполнять справочники.
  participant_id?: number | null;
  store_id?: number | null;
  // Имеют смысл только у расчётов (external_in / external_out).
  counterparty_id?: number | null;
  transit_party_id?: number | null;
  settlement_kind?: SettlementKind | null;
  // Запись остаётся в истории, но выпадает из всех расчётов.
  is_excluded?: boolean;
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

// Период дашборда. Значение по умолчанию выбирает интерфейс — «за всё
// время»; API остаётся на месяце, чтобы не менять молча смысл ответа тому,
// кто просто передал год и месяц.
export type DashboardRange = "month" | "year" | "all";

export interface DashboardAccountBalance {
  account_id: number;
  name: string;
  balance: string;
  // Валюта счёта и тот же остаток в валюте установки по сегодняшнему
  // курсу. Остаток печатается в своей валюте, а пересчёт нужен для итога:
  // сложить евро с рублями иначе нельзя.
  currency: string;
  balance_base: string;
  reserved: string;
  available: string;
  nature: AccountNature;
}

export interface LargestExpense {
  id: number;
  date: string;
  description: string;
  amount: string;
  category_name: string | null;
  account_name: string;
}

export interface DashboardMonthPoint {
  year: number;
  month: number;
  income: string;
  expense: string;
  net: string;
}

export interface DashboardSummary {
  year: number;
  month: number;
  // Границы периода: при выборе «за всё время» интерфейс сам их не знает.
  start_date: string | null;
  end_date: string | null;
  real_income: string;
  spent: string;
  net: string;
  transferred_out: string;
  spending_by_category: CategoryBreakdownItem[];
  // Остатки всегда текущие, независимо от периода.
  accounts: DashboardAccountBalance[];
  // null, когда за период не введено ни часа работы.
  hours_worked: string | null;
  earned_per_hour: string | null;
  largest_expenses: LargestExpense[];
  monthly: DashboardMonthPoint[];
}

export type AssetClass = "investments" | "crypto" | "real_estate" | "vehicles" | "precious_metals" | "other";
// «custom» — не длина, а признак того, что период задан датами.
export type NetWorthRange = "30d" | "90d" | "1y" | "5y" | "all" | "custom";
export type CapitalRole = "income" | "neutral" | "drain";
export type RiskLevel = "low" | "medium" | "high";

export interface Asset {
  // Квартира, в которой живут, и машина, на которой ездят: часть
  // капитала, но не та, на которую можно опереться в решении.
  is_personal_use: boolean;
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
  is_personal_use?: boolean;
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
  is_personal_use?: boolean;
  name?: string;
  asset_class?: AssetClass;
  notes?: string | null;
  capital_role?: CapitalRole;
  monthly_cash_flow?: string | null;
  risk_level?: RiskLevel;
}

/** Одна точка истории: сколько актив стоил на эту дату. По этим точкам
 *  строится график капитала, поэтому правка цены историю не затирает — она
 *  добавляет новую точку. */
export interface AssetValuation {
  id: number;
  value: string;
  as_of_date: string;
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
  /**
   * В какой валюте посчитан ответ и какие есть на выбор.
   *
   * Капитал — состояние, и переводить его нельзя: сто евро на евровой
   * карте это сто евро, а не их сегодняшняя цена. Поэтому не один
   * пересчитанный итог, а по величине на валюту и переключатель между
   * ними.
   */
  currency: string;
  currencies: string[];
  /** Всё, что лежит вне выбранной валюты, — в валюте установки, по
   *  сегодняшнему курсу. Единственное переведённое число здесь: иначе его
   *  не выразить, евро с юанями не складываются. */
  other_base: string;
  /** Итог одной цифрой: выбранная валюта плюс всё остальное. Тоже оценка. */
  total_base: string;
  // Быстрые деньги: счета и наличные минус долг по картам.
  liquid: string;
  // Имущество личного пользования — входит в current, но отдельной строкой.
  personal_use: string;
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
  // Три даты цели: когда начали копить, к какому числу хотелось бы
  // собрать и когда собрали на самом деле (closed_at ниже).
  started_on: string | null;
  planned_on: string | null;
  // Счёт, на котором физически лежат отложенные деньги. Без него счёт не
  // сможет показать «отложено»: непонятно, откуда цель копит.
  account_id: number | null;
  // Активна, достигнута или отменена. Завершение ручное: потратить
  // накопленное — событие, о котором приложению неоткуда узнать, деньги
  // уходят обычной тратой.
  status: GoalStatus;
  // Дата завершения. Пусто, пока копится.
  closed_at: string | null;
  current_amount: string;
  // Сколько всего вносили, без учёта возвратов. У завершённой цели
  // это единственное осмысленное число.
  deposited: string;
  remaining: string;
  percent: number;
  is_reached: boolean;
  /**
   * Три числа из трёх дат — считает сервер.
   *
   * Дней с начала накопления: у завершённой цели до дня сбора, у активной
   * до сегодня. Дней до планируемой даты (минус — просрочка), у
   * завершённой не считается. За сколько собрали на самом деле — только у
   * достигнутой: у отменённой сбора не было.
   */
  days_saving: number | null;
  days_to_plan: number | null;
  days_taken: number | null;
  // Откуда отложено: копить можно с нескольких счетов.
  by_account: GoalReservation[];
}

/** Строка истории накопления. */
export interface GoalContribution {
  id: number;
  amount: string;
  date: string;
  note: string | null;
  account_id: number | null;
  account_name: string | null;
  /** Трата, которой цель была реализована. Такой взнос объясняет, куда
   *  делись отложенные деньги, и поэтому не удаляется — только правится. */
  transaction_id: number | null;
  /** Накоплено на этот день. Считает сервер: правило «по дате, а при
   *  равных датах по порядку ввода» должно быть одно. */
  running_total: string;
}

export interface GoalInput {
  // Завершение цели идёт тем же PATCH, что и переименование: отдельный
  // маршрут «закрыть» описывал бы то же самое вторым способом.
  status?: GoalStatus;
  name: string;
  target_amount: string;
  started_on: string | null;
  planned_on: string | null;
  /** Фактическая дата сбора. Приложение ставит её само при завершении, но
   *  правится руками: «собрал в июне, отметил в августе» — обычное дело. */
  closed_at?: string | null;
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
  /**
   * Операции с этим человеком шли больше чем в одной валюте.
   *
   * Итог посчитан в валюте установки, по курсу дня каждой операции. Это
   * верно в смысле «сколько я в него вложил», но заняв сто евро, ждут
   * обратно сто евро, а не то, сколько они стоили в тот вторник.
   */
  mixed_currencies: boolean;
  last_date: string | null;
}

/** Деньги, прошедшие через счёт насквозь. В расчёты с людьми не входят:
 *  между мной и каждым из них не произошло ничего. */
export interface TransitSummary {
  passed_through: string;
  /** Может быть отрицательным: передал вперёд, ещё не получив. */
  held: string;
}

/**
 * Транзит по одному человеку — по тому, ДЛЯ КОГО шли деньги.
 *
 * Источник, передавший на покупки для кого-то другого, сюда не попадает:
 * он не сторона расчёта, ни он никому не должен, ни ему.
 */
export interface TransitPerson {
  counterparty_id: number;
  name: string;
  received: string;
  spent: string;
  // Плюс — его деньги ещё у вас, минус — вы вложили свои. Не долг.
  balance: string;
  operations: number;
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
  /** Валюта счёта: долг по долларовой карте — это доллары. */
  account_currency: string;
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
  // С какого счёта откладываем (или на какой возвращаем). Пусто — берётся
  // счёт самой цели: в привычном случае «одна цель, одна карта» выбирать
  // нечего.
  account_id?: number | null;
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
  // null у строки, выведенной из плана: своей записи в бюджетах нет,
  // править и удалять её надо в «Планировании».
  budget_id: number | null;
  source: "budget" | "plan";
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
  // Строки наравне с числами: оповещение о платеже называет счёт по имени, а
  // перечислять имена в переводах нельзя — они у каждого свои.
  params: Record<string, number | string>;
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
  // Настроен ли ключ CoinGecko. Указание источника показывается только при
  // нём: без ключа его данных в приложении нет вовсе, и ссылка была бы
  // указанием источника, из которого ничего не взято.
  source_configured: boolean;
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
  // Что показывать при открытии. Хранится на сервере, а не в браузере:
  // установка однопользовательская, и выбор с ноутбука должен действовать
  // с телефона.
  default_dashboard_range: DashboardRange;
  // Счёт, подставляемый в новую операцию. Основная карта одна, и
  // выбирать её каждый раз — лишний шаг на самом частом действии.
  default_account_id: number | null;
  // Показывать ли копейки. В операции они и есть данные; в годовом
  // итоге только удлиняют число.
  show_cents: boolean;
  default_page_size: number;
  group_repeats_by_default: boolean;
  day_dividers_by_default: boolean;
}

export interface HealthStatus {
  status: string;
  version: string;
}


// Планирование. Отличается от бюджета: бюджет — потолок на месяц, который
// предупреждает; план — ожидание на годы, из которого складывается картина
// года.
/**
 * Частота повторения плана. Шаг («каждые N») лежит отдельно, в
 * repeat_every: «ежемесячно» и «раз в квартал» — одна частота с разным
 * шагом.
 */
export type PlanFrequency = "one_off" | "day" | "week" | "month" | "year";

/**
 * Какой день берётся внутри месяца у месячного и годового плана.
 *
 * Чисел 29–31 среди вариантов нет намеренно: «31 февраля» не существует, и
 * вместо молчаливого выбора за человека есть отдельные пункты.
 */
export type PlanMonthDayMode =
  | "day_of_month"
  | "nth_weekday"
  | "last_day"
  | "first_workday"
  | "last_workday";

/**
 * Сумма плана на отрезке времени.
 *
 * Отрезков у плана может быть несколько: категория и способ счёта одни, а
 * сумма меняется — подорожал тариф, сменился оператор. Заметка отвечает на
 * вопрос «почему тут другое число», который через год не вспомнит никто.
 */
export interface PlanPeriod {
  // Есть у сохранённых; у новой строки в форме появляется после записи.
  id?: number;
  // Сумма за одно повторение: в месяц попадает столько, сколько повторений
  // в него уложилось.
  amount: string;
  valid_from: string;
  valid_to: string | null;
  note: string | null;
  // Только про показ в форме: на расчёт не влияет и в таблице года отрезок
  // остаётся на своём месте.
  is_archived: boolean;
}

export interface Plan {
  id: number;
  category_id: number | null;
  category_name: string | null;
  participant_id: number | null;
  kind: PlanFrequency;
  // Шаг: «каждые N». Единица означает «каждый».
  repeat_every: number;
  // Дни недели, 0 — понедельник. Пусто — тот же день недели, с которого
  // план начался.
  weekdays: number[] | null;
  month_day_mode: PlanMonthDayMode | null;
  month_days: number[] | null;
  // 1–5 или −1 для последнего.
  nth_weekday: number | null;
  months: number[] | null;
  // Только для дневного: пропускать субботу и воскресенье.
  skip_weekends: boolean;
  currency: string;
  periods: PlanPeriod[];
  // Только для дневного с шагом в один день: считать по отработанным дням
  // из таблицы времени, а не по календарным.
  workdays_only: boolean;
  note: string | null;
  is_active: boolean;
}

export interface PlanInput {
  category_id: number | null;
  kind: PlanFrequency;
  repeat_every: number;
  weekdays: number[] | null;
  month_day_mode: PlanMonthDayMode | null;
  month_days: number[] | null;
  nth_weekday: number | null;
  months: number[] | null;
  skip_weekends: boolean;
  periods: PlanPeriod[];
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
  /** «Зарплата · Иван» — путь до корня ветки, для подсказки. */
  path: string;
  /** Глубина в дереве: 0 — корень. По ней рисуется отступ. */
  depth: number;
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

export type GoalStatus = "active" | "achieved" | "cancelled";

export interface GoalReservation {
  account_id: number;
  account_name: string;
  amount: string;
}

/** Отрезок на полосе счёта: чем именно занята часть остатка. */
export interface AccountReservation {
  account_id: number;
  goal_id: number;
  goal_name: string;
  amount: string;
}

export interface SimilarTransaction {
  id: number;
  date: string;
  description: string;
  amount: string;
  currency: string;
  account_name: string;
  category_name: string | null;
  // Порядок внутри дня: две поездки на автобусе различаются только им.
  day_order: number;
}

export interface WatchRow {
  category_id: number;
  name: string;
  // «Продукты · Сладкое»: имена категорий не уникальны, и без пути две
  // одинаковые строки не различить.
  path: string;
  kind: CategoryKind;
  // Двенадцать сумм, январь — декабрь.
  months: string[];
  total: string;
  previous_total: string;
}

export interface Watchlist {
  year: number;
  rows: WatchRow[];
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

// Единица измерения с коэффициентом к базовой. Коэффициент нужен на клиенте:
// цена за базовую единицу показывается прямо в поле ввода.
export type UnitKind = "weight" | "volume" | "count" | "length" | "service";

export interface UnitInput {
  name: string;
  kind: UnitKind;
  // Сколько базовых единиц своего вида: г → 0,001 кг.
  factor: string;
  sort_order?: number;
  // Базовая мера вида — та, в которой сравнивают цены. Назначение новой
  // снимает признак с прежней: двух базовых в одном виде быть не может.
  is_base?: boolean;
}

export interface Unit {
  id: number;
  name: string;
  kind: UnitKind;
  factor: string;
  is_base: boolean;
  sort_order: number;
}

// Справочник товаров. Две задачи: подставлять категорию и единицу при вводе
// и склеивать десять чеков в одну кривую цены.
export interface Product {
  id: number;
  name: string;
  unit_id: number | null;
  unit_name: string | null;
  barcode: string | null;
  notes: string | null;
  is_archived: boolean;
  // Насколько строка живая: список товаров без этого — просто список слов.
  purchases: number;
  // Количество и единица последней покупки — подставляются в новую позицию.
  last_quantity: string | null;
  last_unit_id: number | null;
  // Размер упаковки для подстановки — только когда он устоялся: последние
  // две покупки с записанным размером совпали. У молока в литровых пакетах
  // совпадают всегда, у сыра, расфасованного в магазине, — никогда.
  last_pack_size: string | null;
  last_pack_unit_id: number | null;
  last_bought: string | null;
  last_price_per_base_unit: string | null;
  // В каких единицах выражена цена выше: «74 ₽ / л» читается, а
  // «74 ₽ / ед.» заставляет догадываться.
  base_unit_name: string | null;
  // Сколько денег ушло на товар. Кривая цены отвечает «дорожает ли»,
  // это — «сколько мне это стоит». Год скользящий, не календарный.
  spent_total: string;
  spent_year: string;
}

export interface ProductInput {
  name: string;
  unit_id: number | null;
  barcode: string | null;
  notes: string | null;
  is_archived?: boolean;
}

export interface PricePoint {
  date: string;
  // Цена за базовую единицу — то, что делает литры сравнимыми с миллилитрами.
  price_per_base_unit: string;
  quantity: string;
  unit_name: string | null;
  // Размер упаковки, если он был записан: строка читается как «2 шт × 0,9 л».
  pack_size: string | null;
  pack_unit_name: string | null;
  amount: string;
  store_name: string | null;
  transaction_id: number;
}

/**
 * Кривая цены в одной мере.
 *
 * Их у товара столько, сколько мер в нём встретилось. Смешивать нельзя:
 * штука и килограмм — разные величины, и одна кривая на обе показывала
 * падение цены на 91% там, где человек просто записал покупку по-другому.
 */
export interface PriceSeries {
  unit_kind: string | null;
  base_unit_name: string | null;
  points: PricePoint[];
  min_price: string | null;
  max_price: string | null;
  last_price: string | null;
  change_percent: number | null;
}

export interface ProductPriceHistory {
  product_id: number;
  product_name: string;
  // Сначала та мера, в которой покупок больше.
  series: PriceSeries[];
  // Покупки без цены или количества: в кривую не идут, но молчать о них
  // нельзя — иначе непонятно, почему покупок восемь, а точек пять.
  unmeasured: number;
}

// Позиция чека — «что лежало в пакете». Отдельно от разбивки по категориям:
// разбивка обязана сойтись с суммой, позиция не обязана ничему.
export interface TransactionItem {
  id: number;
  position: number;
  product_id: number | null;
  product_name: string | null;
  name: string;
  quantity: string | null;
  unit_id: number | null;
  unit_name: string | null;
  // Размер одной упаковки: «2 шт × 0,9 л». Пусто, когда его не
  // записывали, — у развесного товара это обычное дело.
  pack_size: string | null;
  pack_unit_id: number | null;
  price: string | null;
  amount: string | null;
  note: string | null;
}

export interface TransactionItemInput {
  product_id?: number | null;
  name: string;
  quantity?: string | null;
  unit_id?: number | null;
  // Размер одной упаковки: «2 шт × 0,9 л». Мост между штуками и мерой —
  // без него первое со вторым несравнимо. Необязателен: у развесного
  // товара вес каждой упаковки свой, и забытый вес не повод придумывать
  // его из прошлой покупки.
  pack_size?: string | null;
  pack_unit_id?: number | null;
  price?: string | null;
  amount?: string | null;
  note?: string | null;
}

// Суммы по категории за период. Два числа: own — записанное прямо в неё,
// total — она вместе со всей веткой. Разница показывает, сколько трат
// свалено в корень без выбора подкатегории.
export interface CategoryTotal {
  category_id: number;
  own: string;
  total: string;
  transactions: number;
}

// Инвестиции. Один движок на все семейства активов: партии и списание по
// FIFO одинаковы для акции и для монеты, вкладка — фильтр, а не система.
export type InvestmentKind = "stock" | "bond" | "fund" | "crypto" | "metal" | "other";
export type TradeSide = "buy" | "sell";

export interface InvestmentPortfolio {
  id: number;
  name: string;
  color: string | null;
  is_archived: boolean;
  holdings: number;
  value: string;
  cost_basis: string;
}

export interface InvestmentPortfolioInput {
  name: string;
  color?: string | null;
  is_archived?: boolean;
}

export interface InvestmentHolding {
  id: number;
  portfolio_id: number;
  name: string;
  ticker: string | null;
  kind: InvestmentKind;
  currency: string;
  external_id: string | null;
  risk_level: RiskLevel;
  notes: string | null;
  is_archived: boolean;
  last_price: string | null;
  last_price_at: string | null;
  quantity: string;
  // Во сколько обошлось то, что ещё на руках. Не то же, что вложено: часть
  // вложенного уже продана.
  cost_basis: string;
  invested: string;
  average_cost: string | null;
  // null, когда цена неизвестна: ноль означал бы, что актив обесценился.
  value: string | null;
  unrealised: string | null;
  unrealised_percent: number | null;
  realised: string;
  // Продано больше, чем куплено: пропуск в данных, а не ошибка расчёта.
  oversold: string;
  trades: number;
}

export interface InvestmentHoldingInput {
  portfolio_id: number;
  name: string;
  ticker?: string | null;
  kind: InvestmentKind;
  currency?: string;
  risk_level?: RiskLevel;
  notes?: string | null;
  last_price?: string | null;
  is_archived?: boolean;
}

export interface DisposalLot {
  quantity: string;
  cost_per_unit: string;
  acquired_on: string | null;
}

export interface Disposal {
  trade_id: number;
  trade_date: string;
  quantity: string;
  proceeds: string;
  cost: string;
  realised: string;
  lots: DisposalLot[];
}

export interface InvestmentHoldingDetail extends InvestmentHolding {
  open_lots: DisposalLot[];
  disposals: Disposal[];
}

export interface InvestmentTrade {
  id: number;
  holding_id: number;
  side: TradeSide;
  quantity: string;
  price_per_unit: string;
  fee: string;
  trade_date: string;
  day_order: number;
  account_id: number | null;
  note: string | null;
}

export interface InvestmentTradeInput {
  side: TradeSide;
  quantity: string;
  price_per_unit: string;
  fee?: string;
  trade_date: string;
  account_id?: number | null;
  note?: string | null;
}

/** Что зацепит удаление категории — считается перед вопросом о нём. */
export interface CategoryUsage {
  /** Операций, ссылающихся на категорию строкой или сплитом. */
  transactions: number;
  /** Прямых подкатегорий. Они не удаляются, а всплывают в корень. */
  children: number;
  /** Вся ветка ниже, включая внуков. */
  descendants: number;
  /** Операции в ветке ниже — удаление они переживут. */
  descendant_transactions: number;
}

/**
 * Строка блока «Курсы»: сколько стоит одна единица валюты в валюте
 * установки.
 */
export interface CurrencyRate {
  code: string;
  rate: string | null;
  rate_date: string | null;
  /**
   * Предыдущий известный курс и его дата. Дата здесь не украшение: курсы
   * хранятся только за те дни, когда их грузили, и «прошлый» может
   * оказаться позавчерашним, а может и трёхмесячной давности. Без даты
   * разница читалась бы как дневное движение.
   */
  previous: string | null;
  previous_date: string | null;
  /** Валютой ведётся счёт или записана операция: курс нужен расчётам, и
   *  убрать её из списка наблюдения нельзя. */
  in_use: boolean;
}

/** Валюта в списке наблюдения — так он приходит из справочника. */
export interface WatchedCurrency {
  code: string;
  symbol: string | null;
  name: string | null;
  is_active: boolean;
  rate: string | null;
  rate_date: string | null;
}

/** Итог загрузки курсов на дату. */
export interface RateSyncResult {
  saved: number;
  rate_date: string;
  message: string;
  /** Операций, досчитанных загруженными курсами. */
  recomputed: number;
}

/** Итог добора курсов за прошедшие даты. */
export interface BackfillResult {
  dates: number;
  saved: number;
  recomputed: number;
  /** Осталось дат без курса: больше нуля — стоит нажать ещё раз. */
  remaining: number;
}
