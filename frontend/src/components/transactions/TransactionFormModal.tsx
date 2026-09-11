import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { CategoryPicker } from "@/components/categories/CategoryPicker";
import { ItemsEditor } from "@/components/transactions/ItemsEditor";
import {
  useCounterparties,
  useCreateCounterparty,
  useCreateParticipant,
  useCreateStore,
  useParticipants,
  useStores,
} from "@/hooks/useDirectories";
import { TagInput } from "@/components/transactions/TagInput";
import { useAccounts } from "@/hooks/useAccounts";
import { useCategories } from "@/hooks/useCategories";
import { useCreateTransaction, useUpdateTransaction } from "@/hooks/useTransactions";
import { useTranslation } from "@/lib/i18n";
import {
  buildHierarchicalCategories,
  translateCategoryName,
} from "@/lib/categoryLabels";
import { fetchSimilarTransactions } from "@/api/transactions";
import type { SimilarTransaction } from "@/types";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { useAppSettings } from "@/hooks/useSettings";
import { DirectoryPicker } from "@/components/transactions/DirectoryPicker";
import { formatCurrency } from "@/lib/format";
import type {
  Tag,
  Transaction,
  TransactionInput,
  SettlementKind,
  TransactionItemInput,
  TransactionSplitInput,
  TransactionType,
} from "@/types";

interface TransactionFormModalProps {
  open: boolean;
  onClose: () => void;
  transaction?: Transaction | null;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

/** Дата последней заведённой операции — на время сеанса.
 *
 * Заносят историю пачками: сегодня вспомнил неделю назад, завтра — ещё
 * три дня. Подставлять сегодняшнее число каждый раз значит заставлять
 * человека выбирать одну и ту же прошлую дату по десять раз подряд.
 *
 * Именно сеанс, а не настройка: назавтра приложение должно снова
 * открываться на сегодняшнем дне, иначе запись «на автомате» уедет в
 * прошлое, и человек этого не заметит. */
const LAST_DATE_KEY = "aurum:last-transaction-date";

function rememberedDate(): string {
  try {
    return sessionStorage.getItem(LAST_DATE_KEY) || todayIso();
  } catch {
    // Приватное окно или отключённое хранилище — просто сегодня.
    return todayIso();
  }
}

function rememberDate(date: string): void {
  try {
    sessionStorage.setItem(LAST_DATE_KEY, date);
  } catch {
    // Не запомнилось — не беда, поле останется заполненным вручную.
  }
}

const EMPTY_FORM = {
  type: "expense" as TransactionType,
  account_id: "",
  category_id: "",
  transfer_account_id: "",
  amount: "",
  description: "",
  date: todayIso(),
  // Кто, где и с кем. Все три необязательны: быстрый ввод не должен требовать
  // заполнять справочники, а поля, которые никто не заполняет, — это те же
  // 43 неиспользованные подкатегории, на которых сгорела исходная таблица.
  participant_id: "",
  store_id: "",
  counterparty_id: "",
  settlement_kind: "" as SettlementKind | "",
  // «Не учитывать»: запись остаётся в истории, но выпадает из всех расчётов.
  // Ошибочный перевод, задвоенная строка, тестовая операция.
  is_excluded: false,
};

// Расчёты с людьми — отдельные виды операции, а не расход с пометкой.
// Деньги, переданные брату, ушли со счёта, но тратой не были, и складывать
// их с покупками значило бы завысить расходы на всю сумму помощи.
const SETTLEMENT_TYPES: TransactionType[] = ["external_out", "external_in"];

interface SplitRowState {
  key: string;
  category_id: string;
  amount: string;
  note: string;
}

function emptySplitRow(): SplitRowState {
  return { key: crypto.randomUUID(), category_id: "", amount: "", note: "" };
}

// Cents, not floats — a plain Number sum of "0.10" + "0.20" style amounts can
// drift from the transaction total by fractions of a cent, which would
// falsely trip the "must add up exactly" check the backend also enforces.
function toCents(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

export function TransactionFormModal({ open, onClose, transaction }: TransactionFormModalProps) {
  const { t, language } = useTranslation();
  const { data: accounts } = useAccounts();
  const { data: categories } = useCategories();
  const createTransaction = useCreateTransaction();
  const updateTransaction = useUpdateTransaction();

  const [form, setForm] = useState(EMPTY_FORM);
  const [tags, setTags] = useState<Tag[]>([]);
  // Категории операции одним списком. Одна строка — обычная операция с
  // одной категорией; две и больше — разбивка, и тогда у каждой строки
  // своя сумма.
  //
  // Раньше это были два режима с переключателем: «одна категория» и
  // «несколько». Переключатель заодно требовал сначала выбрать категорию
  // верхнего уровня, а доли разрешал только внутри неё — то есть ноутбук
  // и клавиатуру из одного чека разложить было нельзя. Режимов больше нет:
  // добавил строку — стало разбиение, убрал — снова одна категория.
  const [categoryRows, setCategoryRows] = useState<SplitRowState[]>([emptySplitRow()]);
  const [error, setError] = useState<string | null>(null);
  const { data: participants } = useParticipants();
  const { data: stores } = useStores();
  const { data: counterparties } = useCounterparties();
  // Состав чека. Отдельно от разбивки по категориям и вместе с ней:
  // разбивка делит деньги и обязана сойтись с суммой, позиции описывают
  // покупку и сходиться не обязаны ничему.
  const [items, setItems] = useState<TransactionItemInput[]>([]);

  useEffect(() => {
    if (!open) return;
    if (transaction) {
      const hasSplits = transaction.splits.length > 0;
      setForm({
        type: transaction.type,
        account_id: String(transaction.account_id),
        category_id: !hasSplits && transaction.category_id ? String(transaction.category_id) : "",
        transfer_account_id: transaction.transfer_account_id ? String(transaction.transfer_account_id) : "",
        amount: transaction.amount,
        description: transaction.description ?? "",
        date: transaction.date,
        participant_id: transaction.participant_id ? String(transaction.participant_id) : "",
        store_id: transaction.store_id ? String(transaction.store_id) : "",
        counterparty_id: transaction.counterparty_id ? String(transaction.counterparty_id) : "",
        settlement_kind: transaction.settlement_kind ?? "",
        is_excluded: transaction.is_excluded,
      });
      setTags(transaction.tags);
      setItems(
        transaction.items.map((item) => ({
          product_id: item.product_id,
          name: item.name,
          quantity: item.quantity,
          unit_id: item.unit_id,
          price: item.price,
          amount: item.amount,
          note: item.note,
        })),
      );
      setCategoryRows(
        hasSplits
          ? transaction.splits.map((split) => ({
              key: String(split.id),
              category_id: split.category_id ? String(split.category_id) : "",
              amount: split.amount,
              note: split.note ?? "",
            }))
          : [
              {
                ...emptySplitRow(),
                category_id: transaction.category_id ? String(transaction.category_id) : "",
              },
            ]
      );
    } else {
      // Счёт по умолчанию — «основная карта» из настроек. Первый в
      // списке остаётся запасным вариантом: пока настройка не задана,
      // поведение прежнее, а не пустое поле.
      const preferred =
        settings?.default_account_id &&
        (accounts ?? []).some((account) => account.id === settings.default_account_id)
          ? String(settings.default_account_id)
          : accounts?.[0]
            ? String(accounts[0].id)
            : "";
      // Дата — та, что выбрали в прошлый раз за этот сеанс. Остальное
      // пустое: счёт подставляется из настроек, сумма и описание у каждой
      // операции свои.
      setForm({ ...EMPTY_FORM, account_id: preferred, date: rememberedDate() });
      setTags([]);
      setItems([]);
      setCategoryRows([emptySplitRow()]);
    }
    setError(null);
  }, [open, transaction, accounts]);

  const kindCategories = (categories ?? []).filter((category) =>
    form.type === "income" ? category.kind === "income" : category.kind === "expense"
  );
  // Subcategories are listed right under their parent (not scattered by
  // name) so the hierarchy set up on the Categories page reads the same way
  // here.
  const relevantCategories = buildHierarchicalCategories(kindCategories, language);

  const confirm = useConfirm();
  // Справочники пополняются прямо отсюда: уходить за этим в другой
  // раздел значит прерывать ввод операции ради заведения магазина.
  const createParticipant = useCreateParticipant();
  const createStore = useCreateStore();
  const createCounterparty = useCreateCounterparty();
  const { data: settings } = useAppSettings();
  const isSaving = createTransaction.isPending || updateTransaction.isPending;

  function updateCategoryRow(key: string, patch: Partial<SplitRowState>) {
    setCategoryRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function addCategoryRow() {
    setCategoryRows((prev) => {
      // Первой строке при переходе к разбивке проставляется остаток: чаще
      // всего вторая доля — это «а вот столько было на другое», и остальное
      // остаётся на первой. Уже введённую вручную сумму не трогаем.
      const allocated = prev.reduce((sum, row) => sum + toCents(row.amount), 0);
      const rest = toCents(form.amount) - allocated;
      const filled =
        prev.length === 1 && !prev[0].amount && rest > 0
          ? [{ ...prev[0], amount: (rest / 100).toFixed(2) }]
          : prev;
      return [...filled, emptySplitRow()];
    });
  }

  function removeCategoryRow(key: string) {
    setCategoryRows((prev) => {
      if (prev.length <= 1) return prev;
      const next = prev.filter((row) => row.key !== key);
      // Осталась одна строка — это снова обычная операция с одной
      // категорией, и сумма доли теряет смысл: она равна сумме операции.
      return next.length === 1 ? [{ ...next[0], amount: "", note: "" }] : next;
    });
  }

  const isSettlement = SETTLEMENT_TYPES.includes(form.type);
  // Разбивка — это просто «строк больше одной». Отдельного признака нет:
  // два источника правды про одно и то же расходились бы при каждой правке.
  const isSplit = form.type !== "transfer" && categoryRows.length > 1;
  const splitAllocatedCents = categoryRows.reduce((sum, row) => sum + toCents(row.amount), 0);
  const splitRemainingCents = toCents(form.amount) - splitAllocatedCents;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!form.account_id) {
      setError(t("transactions.form.errorSelectAccount"));
      return;
    }
    if (form.type === "transfer" && !form.transfer_account_id) {
      setError(t("transactions.form.errorSelectDestination"));
      return;
    }
    if (form.type === "transfer" && form.transfer_account_id === form.account_id) {
      setError(t("transactions.form.errorSameAccount"));
      return;
    }

    // Undefined -> leave the transaction's existing splits untouched on
    // update, and create a normal single-category transaction. [] -> clears
    // splits that used to be there (the user turned split mode off, or
    // switched the transaction to a transfer, which can't carry splits).
    // undefined — оставить разбивку операции как была (при правке) и
    // записать обычную операцию с одной категорией. [] — стереть разбивку,
    // которая там была: строк снова одна, или операция стала переводом.
    let splits: TransactionSplitInput[] | undefined;
    const singleCategory = categoryRows.length === 1 ? categoryRows[0].category_id : "";
    if (isSplit) {
      const filledRows = categoryRows.filter((row) => row.category_id || row.amount);
      if (filledRows.length < 2) {
        setError(t("transactions.form.errorSplitMinRows"));
        return;
      }
      if (filledRows.some((row) => !row.category_id || !row.amount || Number(row.amount) <= 0)) {
        setError(t("transactions.form.errorSplitIncomplete"));
        return;
      }
      const allocatedCents = filledRows.reduce((sum, row) => sum + toCents(row.amount), 0);
      if (allocatedCents !== toCents(form.amount)) {
        setError(t("transactions.form.errorSplitMismatch"));
        return;
      }
      splits = filledRows.map((row) => ({
        category_id: Number(row.category_id),
        amount: row.amount,
        note: row.note || null,
      }));
    } else if (transaction && transaction.splits.length > 0) {
      splits = [];
    }

    // Дата запоминается до конца сеанса — следующая операция откроется на
    // ней же. Запоминается при отправке, а не при наборе: набранное и
    // брошенное число выбором не было.
    rememberDate(form.date);

    const payload: TransactionInput = {
      type: form.type,
      account_id: Number(form.account_id),
      category_id:
        form.type === "transfer" || (splits && splits.length > 0)
          ? null
          : singleCategory
            ? Number(singleCategory)
            : null,
      transfer_account_id: form.type === "transfer" ? Number(form.transfer_account_id) : null,
      amount: form.amount,
      description: form.description.trim() || null,
      date: form.date,
      tag_ids: tags.map((tag) => tag.id),
      participant_id: form.participant_id ? Number(form.participant_id) : null,
      store_id: form.store_id ? Number(form.store_id) : null,
      // Контрагент и признак возвратности имеют смысл только у расчётов:
      // отправлять их у обычной покупки значило бы записать связь, которой
      // нет, и человек потом гадал бы, откуда взялся долг.
      counterparty_id: isSettlement && form.counterparty_id ? Number(form.counterparty_id) : null,
      settlement_kind: isSettlement && form.settlement_kind ? form.settlement_kind : null,
      is_excluded: form.is_excluded,
      splits,
      // Позиции без названия не отправляются: пустая строка, добавленная и
      // не заполненная, — не позиция.
      items: items.filter((item) => item.name.trim() !== ""),
    };

    try {
      if (transaction) {
        await updateTransaction.mutateAsync({ id: transaction.id, input: payload });
      } else {
        if (!(await confirmNoDuplicate(payload))) return;
        await createTransaction.mutateAsync(payload);
      }
      onClose();
    } catch {
      setError(t("transactions.form.saveError"));
    }
  }

  /**
   * Спрашивает, если такая операция в этом дне уже записана.
   *
   * Нужно из-за того, как учёт ведут на самом деле: не подряд, а
   * вперемешку — сегодняшнее сразу, вчерашнее потом. При таком вводе одна
   * покупка легко записывается дважды и не бросается в глаза, потому что в
   * списке эти две строки оказываются не рядом.
   *
   * Спрашивает, а не запрещает: две поездки на автобусе за день —
   * настоящий повтор, и человек его помнит. Показываются сами найденные
   * строки, чтобы решать было по чему.
   */
  async function confirmNoDuplicate(payload: TransactionInput): Promise<boolean> {
    let similar: SimilarTransaction[];
    try {
      similar = await fetchSimilarTransactions({
        date: payload.date,
        type: payload.type,
        amount: payload.amount,
        description: payload.description ?? "",
        category_id: payload.category_id,
      });
    } catch {
      // Проверка не удалась — записываем как обычно. Предупреждение,
      // которое из-за собственного сбоя мешает сохранить операцию, вредит
      // больше, чем пропущенный повтор.
      return true;
    }
    if (similar.length === 0) return true;

    return confirm({
      title: t("transactions.duplicateTitle"),
      tone: "danger",
      confirmLabel: t("transactions.duplicateConfirm"),
      message: (
        <span className="block">
          {t("transactions.duplicateQuestion", { count: similar.length })}
          <span className="mt-2 block divide-y divide-border rounded-lg border border-border">
            {similar.map((item) => (
              <span key={item.id} className="flex items-baseline justify-between gap-3 px-2.5 py-1.5">
                <span className="min-w-0 truncate text-text-primary">
                  {item.description || t("transactions.form.noCategory")}
                  <span className="block text-xs text-text-muted">
                    {item.account_name}
                    {item.category_name ? ` · ${translateCategoryName(item.category_name)}` : ""}
                  </span>
                </span>
                <span className="shrink-0 tabular-nums text-text-primary">
                  {formatCurrency(item.amount, item.currency)}
                </span>
              </span>
            ))}
          </span>
        </span>
      ),
    });
  }

  return (
    <Dialog
      wide
      open={open}
      onClose={onClose}
      title={transaction ? t("transactions.form.editTitle") : t("transactions.form.newTitle")}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="type">{t("transactions.form.typeLabel")}</Label>
          <Select
            id="type"
            value={form.type}
            onChange={(event) => {
              const nextType = event.target.value as TransactionType;
              setForm((prev) => ({ ...prev, type: nextType, category_id: "" }));
              // Категории расхода и дохода не пересекаются: оставить
              // выбранное значило бы отправить чужую категорию.
              setCategoryRows([emptySplitRow()]);
            }}
          >
            <option value="expense">{t("transactions.form.typeExpense")}</option>
            <option value="income">{t("transactions.form.typeIncome")}</option>
            <option value="transfer">{t("transactions.form.typeTransfer")}</option>
            {/* Расчёты с людьми двигают баланс, но не считаются заработком
                или тратой — иначе помощь родителям выглядела бы расходом на
                себя, а полученное от жены — доходом. */}
            <option value="external_out">{t("transactions.form.typeExternalOut")}</option>
            <option value="external_in">{t("transactions.form.typeExternalIn")}</option>
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="amount">{t("transactions.form.amountLabel")}</Label>
            <Input
              id="amount"
              type="number"
              step="0.01"
              min="0.01"
              required
              value={form.amount}
              onChange={(event) => setForm((prev) => ({ ...prev, amount: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="date">{t("transactions.form.dateLabel")}</Label>
            <Input
              id="date"
              type="date"
              required
              value={form.date}
              onChange={(event) => setForm((prev) => ({ ...prev, date: event.target.value }))}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="description">{t("transactions.form.descriptionLabel")}</Label>
          {/* Без required. Описание необязательно с beta.4: в исходной
              таблице это была вторая строка записи, а не заметка, и у
              большинства покупок сказать сверх категории нечего.
              Ограничение сняли в схеме, а в форме оно осталось — браузер
              продолжал требовать текст, которого приложение уже не ждёт. */}
          <Input
            id="description"
            placeholder={t("transactions.form.descriptionPlaceholder")}
            value={form.description}
            onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="account">{t("transactions.form.accountLabel")}</Label>
          <Select
            id="account"
            required
            value={form.account_id}
            onChange={(event) => setForm((prev) => ({ ...prev, account_id: event.target.value }))}
          >
            <option value="" disabled>
              {t("transactions.form.selectAccount")}
            </option>
            {accounts?.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
        </div>

        {isSettlement ? (
          <div className="space-y-3 rounded-lg border border-border p-3">
            <div>
              <Label htmlFor="counterparty">{t("transactions.form.counterpartyLabel")}</Label>
              <DirectoryPicker
                id="counterparty"
                options={counterparties ?? []}
                value={form.counterparty_id}
                onChange={(value) => setForm((prev) => ({ ...prev, counterparty_id: value }))}
                placeholder={t("transactions.form.selectCounterparty")}
                onCreate={async (name) => (await createCounterparty.mutateAsync({ name })).id}
              />
            </div>

            <div>
              <Label htmlFor="settlement_kind">{t("transactions.form.settlementKindLabel")}</Label>
              <Select
                id="settlement_kind"
                required
                value={form.settlement_kind}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, settlement_kind: event.target.value as SettlementKind }))
                }
              >
                <option value="" disabled>
                  {t("transactions.form.selectSettlementKind")}
                </option>
                {/* Признак стоит на операции, а не на человеке: один и тот
                    же человек и дарит, и одалживает. */}
                <option value="gift">{t("transactions.form.settlementGift")}</option>
                <option value={form.type === "external_out" ? "loan_out" : "loan_in"}>
                  {t("transactions.form.settlementLoan")}
                </option>
                <option value="repayment">{t("transactions.form.settlementRepayment")}</option>
                {/* Транзит: деньги прошли через счёт и ушли дальше. Не
                    подарок — считается так же, но называется честно:
                    «получено подарками 50 000» врёт, если это была касса на
                    общий подарок. */}
                <option value="transit">{t("transactions.form.settlementTransit")}</option>
              </Select>
              <p className="mt-1 text-xs text-text-muted">{t("transactions.form.settlementHint")}</p>
            </div>

            {/* Категория у движения с человеком. Раньше её здесь не было
                вовсе, и покупку на чужие деньги нельзя было ни на что
                повесить — оставалось писать «продукты» в описание.
                Необязательна: у «занял до зарплаты» ей взяться неоткуда.

                В траты и в круг категорий такая запись по-прежнему не
                попадает — она и не трата: деньги были не свои. Категория
                здесь — чтобы найти покупку потом и увидеть её в списке
                рядом с остальными продуктовыми. */}
            <div>
              <Label htmlFor="settlement-category">{t("transactions.form.categoryLabel")}</Label>
              <CategoryPicker
                id="settlement-category"
                categories={relevantCategories}
                value={categoryRows[0]?.category_id ?? ""}
                onChange={(value) =>
                  setCategoryRows((prev) => [{ ...(prev[0] ?? emptySplitRow()), category_id: value }])
                }
                placeholder={t("transactions.form.noCategory")}
                emptyLabel={t("transactions.form.noCategory")}
              />
              <p className="mt-1 text-xs text-text-muted">{t("transactions.form.settlementCategoryHint")}</p>
            </div>
          </div>
        ) : form.type === "transfer" ? (
          <div>
            <Label htmlFor="transfer_account">{t("transactions.form.transferAccountLabel")}</Label>
            <Select
              id="transfer_account"
              required
              value={form.transfer_account_id}
              onChange={(event) => setForm((prev) => ({ ...prev, transfer_account_id: event.target.value }))}
            >
              <option value="" disabled>
                {t("transactions.form.selectAccount")}
              </option>
              {accounts
                ?.filter((account) => String(account.id) !== form.account_id)
                .map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
            </Select>
          </div>
        ) : (
          <div>
            <Label htmlFor="category">{t("transactions.form.categoryLabel")}</Label>

            {/* Один список: одна строка — обычная категория, две и больше —
                разбивка. Ветки категорий не ограничены ничем: ноутбук и
                клавиатура из одного чека лежат в разных ветках, и это
                обычная покупка, а не исключение. */}
            <div className="space-y-2">
              {categoryRows.map((row, index) => (
                <div key={row.key} className={isSplit ? "space-y-1.5 rounded-lg border border-border bg-surface-1 p-2" : undefined}>
                  <div className="flex items-center gap-1.5">
                    <CategoryPicker
                      id={index === 0 ? "category" : undefined}
                      className="min-w-0 flex-1"
                      categories={relevantCategories}
                      value={row.category_id}
                      onChange={(value) => updateCategoryRow(row.key, { category_id: value })}
                      placeholder={t("transactions.form.noCategory")}
                      // Пустой выбор доступен только у единственной строки:
                      // доля разбивки без категории — это просто потерянные
                      // деньги в отчёте.
                      emptyLabel={isSplit ? undefined : t("transactions.form.noCategory")}
                    />
                    {isSplit && (
                      <>
                        <Input
                          type="number"
                          step="0.01"
                          min="0.01"
                          className="w-24 shrink-0"
                          placeholder={t("transactions.form.amountLabel")}
                          value={row.amount}
                          onChange={(event) => updateCategoryRow(row.key, { amount: event.target.value })}
                        />
                        <button
                          type="button"
                          aria-label={t("transactions.form.splitRemoveRow")}
                          onClick={() => removeCategoryRow(row.key)}
                          className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                        >
                          <X size={15} />
                        </button>
                      </>
                    )}
                  </div>
                  {isSplit && (
                    <Input
                      className="text-xs"
                      placeholder={t("transactions.form.splitNotePlaceholder")}
                      value={row.note}
                      onChange={(event) => updateCategoryRow(row.key, { note: event.target.value })}
                    />
                  )}
                </div>
              ))}

              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={addCategoryRow}
                  className="flex items-center gap-1 rounded-md py-1 text-xs text-series-1 hover:underline"
                >
                  <Plus size={14} />
                  {t("transactions.form.splitAddRow")}
                </button>
                {/* Остаток — только при разбивке: у одной категории он
                    всегда ноль по построению, и строка была бы шумом. */}
                {isSplit && (
                  <p className={`text-xs ${splitRemainingCents === 0 ? "text-success" : "text-text-muted"}`}>
                    {splitRemainingCents > 0
                      ? t("transactions.form.splitRemainingLabel", {
                          amount: formatCurrency(splitRemainingCents / 100),
                        })
                      : splitRemainingCents < 0
                        ? t("transactions.form.splitOverAllocatedLabel", {
                            amount: formatCurrency(Math.abs(splitRemainingCents) / 100),
                          })
                        : t("transactions.form.splitFullyAllocatedLabel")}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        <div>
          <Label htmlFor="transaction-tags">{t("transactions.form.tagsLabel")}</Label>
          <TagInput value={tags} onChange={setTags} />
        </div>

        {/* Кто и где. Оба поля необязательны и стоят внизу: они уточняют
            запись, а не определяют её, и требовать их при быстром вводе
            значило бы отпугнуть от ввода вообще. */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="participant">{t("transactions.form.participantLabel")}</Label>
            <DirectoryPicker
              id="participant"
              options={participants ?? []}
              value={form.participant_id}
              onChange={(value) => setForm((prev) => ({ ...prev, participant_id: value }))}
              emptyLabel={t("transactions.form.noParticipant")}
              placeholder={t("transactions.form.participantPlaceholder")}
              onCreate={async (name) => (await createParticipant.mutateAsync({ name })).id}
            />
          </div>
          <div>
            <Label htmlFor="store">{t("transactions.form.storeLabel")}</Label>
            <DirectoryPicker
              id="store"
              options={stores ?? []}
              value={form.store_id}
              onChange={(value) => setForm((prev) => ({ ...prev, store_id: value }))}
              emptyLabel={t("transactions.form.noStore")}
              placeholder={t("transactions.form.storePlaceholder")}
              onCreate={async (name) => (await createStore.mutateAsync({ name })).id}
            />
          </div>
        </div>

        {/* «Не учитывать»: запись остаётся в истории, но выпадает из всех
            расчётов. Ошибочный перевод, задвоенная строка, тестовая
            операция — удалять их нельзя, они были, но и считать нельзя. */}
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_excluded}
            onChange={(event) => setForm((prev) => ({ ...prev, is_excluded: event.target.checked }))}
            className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
          />
          <span>
            {t("transactions.form.excludedLabel")}
            <span className="block text-xs text-text-muted">{t("transactions.form.excludedHint")}</span>
          </span>
        </label>

        {/* Состав чека — только у трат: у зарплаты нет позиций, а у перевода
            между своими счетами тем более. */}
        {form.type === "expense" && (
          <ItemsEditor items={items} onChange={setItems} total={form.amount} />
        )}

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
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
