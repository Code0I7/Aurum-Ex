import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { Input, Label, LabelWithHelp, Select } from "@/components/ui/Input";
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
import { checkTransferMatch } from "@/api/transferMatches";
import { TransferMatchSideRow } from "@/components/transactions/TransferMatchesNotice";
import type { SimilarTransaction, TransferCounterpart } from "@/types";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { useAppSettings } from "@/hooks/useSettings";
import { DirectoryPicker } from "@/components/transactions/DirectoryPicker";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
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
  // Сколько пришло на счёт получателя. Заполняется только у перевода между
  // разными валютами — см. поле в разметке ниже.
  transfer_amount: "",
  description: "",
  date: todayIso(),
  // Кто, где и с кем. Все три необязательны: быстрый ввод не должен требовать
  // заполнять справочники, а поля, которые никто не заполняет, — это те же
  // 43 неиспользованные подкатегории, на которых сгорела исходная таблица.
  participant_id: "",
  store_id: "",
  counterparty_id: "",
  settlement_kind: "" as SettlementKind | "",
  transit_party_id: "",
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

/** Доля одного человека в операции, разделённой между несколькими: долг
 *  вернули трое одним переводом. */
interface PersonRowState {
  key: string;
  counterparty_id: string;
  amount: string;
}

function emptyPersonRow(): PersonRowState {
  return { key: crypto.randomUUID(), counterparty_id: "", amount: "" };
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
  // Разбивка между людьми — своим состоянием, как и строки категорий: это
  // список переменной длины, а не поле формы. Пустой список означает
  // «делить не между кем», и тогда человек называется обычным полем.
  const [peopleRows, setPeopleRows] = useState<PersonRowState[]>([]);
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
  // Справочники — вместе с архивными записями. Не для того, чтобы их
  // предлагать: DirectoryPicker покажет архивную, только если она уже стоит
  // в операции. Без архива человек, отправленный туда, в открытой операции
  // выглядел пустым полем.
  const { data: participants } = useParticipants(true);
  const { data: stores } = useStores(true);
  const { data: counterparties } = useCounterparties(true);
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
        transfer_amount: transaction.transfer_amount ?? "",
        description: transaction.description ?? "",
        date: transaction.date,
        participant_id: transaction.participant_id ? String(transaction.participant_id) : "",
        store_id: transaction.store_id ? String(transaction.store_id) : "",
        counterparty_id: transaction.counterparty_id ? String(transaction.counterparty_id) : "",
        settlement_kind: transaction.settlement_kind ?? "",
        transit_party_id: transaction.transit_party_id?.toString() ?? "",
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
      setPeopleRows(
        transaction.counterparty_splits.map((split) => ({
          key: String(split.id),
          counterparty_id: split.counterparty_id ? String(split.counterparty_id) : "",
          amount: split.amount,
        }))
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
      setPeopleRows([]);
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

  // Перевод между счетами в разных валютах. Только тогда «сколько ушло» и
  // «сколько пришло» — два разных числа: внутри одной валюты это одно и то
  // же, и второе поле означало бы возможность разойтись с самим собой.
  const sourceAccount = accounts?.find((account) => String(account.id) === form.account_id);
  /**
   * Дата раньше дня, с которого счёт считается открытым.
   *
   * Начальный остаток — это деньги, лежавшие на счёте до первой записи, и всё,
   * что было раньше, в него уже входит. Операция с такой датой прибавится к
   * нему сверху, то есть посчитается дважды.
   *
   * Предупреждение, а не запрет: неверной может оказаться как раз дата
   * открытия счёта, и решать это человеку.
   */
  const beforeOpening =
    sourceAccount?.opening_date && form.date && form.date < sourceAccount.opening_date
      ? sourceAccount.opening_date
      : null;
  const destinationAccount = accounts?.find(
    (account) => String(account.id) === form.transfer_account_id
  );
  const crossCurrencyTransfer =
    form.type === "transfer" &&
    sourceAccount !== undefined &&
    destinationAccount !== undefined &&
    sourceAccount.currency !== destinationAccount.currency;

  const isSettlement = SETTLEMENT_TYPES.includes(form.type);
  // Операция разделена между людьми: строк больше одной. Отдельного
  // признака нет по той же причине, что и у категорий — два источника
  // правды про одно и то же расходятся при первой правке.
  const isPeopleSplit = isSettlement && peopleRows.length > 1;
  const peopleAllocatedCents = peopleRows.reduce((sum, row) => sum + toCents(row.amount), 0);
  const peopleRemainingCents = toCents(form.amount) - peopleAllocatedCents;
  const isTransit = isSettlement && form.settlement_kind === "transit";
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
    // Разбивка между людьми: либо её нет вовсе, либо она сходится с суммой
    // и в ней не меньше двух человек. Сервер проверяет то же самое, но
    // ответ оттуда — общая ошибка сохранения, а здесь видно, чего не
    // хватает.
    const filledPeople = peopleRows.filter((row) => row.counterparty_id || row.amount);
    if (filledPeople.length > 0) {
      if (filledPeople.length < 2) {
        setError(t("transactions.form.errorPeopleMinRows"));
        return;
      }
      if (filledPeople.some((row) => !row.counterparty_id || toCents(row.amount) <= 0)) {
        setError(t("transactions.form.errorPeopleIncomplete"));
        return;
      }
      const allocated = filledPeople.reduce((sum, row) => sum + toCents(row.amount), 0);
      if (allocated !== toCents(form.amount)) {
        setError(t("transactions.form.errorPeopleSum"));
        return;
      }
    }

    if (crossCurrencyTransfer && !form.transfer_amount) {
      setError(t("transactions.form.errorTransferAmount"));
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
      // Только когда валюты счетов правда разные: у обычного перевода это
      // была бы копия суммы, а копия однажды разойдётся с оригиналом.
      transfer_amount: crossCurrencyTransfer ? form.transfer_amount : null,
      description: form.description.trim() || null,
      date: form.date,
      tag_ids: tags.map((tag) => tag.id),
      participant_id: form.participant_id ? Number(form.participant_id) : null,
      store_id: form.store_id ? Number(form.store_id) : null,
      // Контрагент и признак возвратности имеют смысл только у расчётов:
      // отправлять их у обычной покупки значило бы записать связь, которой
      // нет, и человек потом гадал бы, откуда взялся долг.
      // Контрагент и разбивка — взаимоисключающие ответы на «от кого»:
      // при разбивке поле обязано быть пустым, иначе операция посчиталась
      // бы дважды.
      counterparty_id:
        isSettlement && !isPeopleSplit && form.counterparty_id
          ? Number(form.counterparty_id)
          : null,
      counterparty_splits: isPeopleSplit
        ? filledPeople.map((row) => ({
            counterparty_id: Number(row.counterparty_id),
            amount: row.amount,
          }))
        : [],
      settlement_kind: isSettlement && form.settlement_kind ? form.settlement_kind : null,
      // Вторая сторона есть только у транзита: у подарка и займа деньги
      // и правда между двумя, и лишнее поле там означало бы третьего.
      transit_party_id:
        isTransit && form.transit_party_id ? Number(form.transit_party_id) : null,
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
        const transferAnswer = await confirmNotRecordedTransfer(payload);
        if (transferAnswer === "cancelled") return;
        // Про этот перевод уже спросили — второй вопрос о том же дне был бы
        // о том же самом и только раздражал бы.
        if (transferAnswer === "none" && !(await confirmNoDuplicate(payload))) return;
        await createTransaction.mutateAsync(payload);
      }
      onClose();
    } catch {
      setError(t("transactions.form.saveError"));
    }
  }

  /**
   * Спрашивает, если этот перевод между своими счетами, похоже, уже записан.
   *
   * Перевод заносят по выпискам, а выписок две — по банку на каждую
   * сторону. Идя по выписке второго банка, человек видит приход и заносит
   * его, не помня, что перевод уже записан из первой выписки. Узнать об
   * этом до записи лучше, чем разбирать повтор потом.
   *
   * Спрашивает, а не запрещает: совпадение суммы и дня бывает честным.
   * Если записали всё равно, пара появится в «Повторах переводов» на
   * странице операций, и там её можно объединить.
   *
   * Ответ «none» — спрашивать было не о чем.
   */
  async function confirmNotRecordedTransfer(
    payload: TransactionInput
  ): Promise<"none" | "confirmed" | "cancelled"> {
    // Те же правила, что у поиска пар на сервере: разделённая трата,
    // чек и «не учитывать» половиной перевода не бывают.
    if (!["transfer", "income", "expense"].includes(payload.type)) return "none";
    if (payload.is_excluded || (payload.splits?.length ?? 0) > 0 || (payload.items?.length ?? 0) > 0) {
      return "none";
    }

    let found: TransferCounterpart[];
    try {
      found = await checkTransferMatch({
        type: payload.type,
        account_id: payload.account_id,
        amount: payload.amount,
        date: payload.date,
        transfer_account_id: payload.transfer_account_id,
        transfer_amount: payload.transfer_amount,
      });
    } catch {
      // Как и у проверки повторов дня: сбой проверки не должен мешать
      // сохранить операцию.
      return "none";
    }
    if (found.length === 0) return "none";

    const recorded = found.some((item) => item.kind !== "halves");
    const confirmed = await confirm({
      title: t("transferMatches.formTitle"),
      tone: "danger",
      confirmLabel: t("transactions.duplicateConfirm"),
      message: (
        <span className="block">
          {t(recorded ? "transferMatches.formRecorded" : "transferMatches.formHalf")}
          <span className="mt-2 block divide-y divide-border rounded-lg border border-border px-2.5 py-1.5">
            {found.map((item) => (
              <TransferMatchSideRow key={item.transaction.id} side={item.transaction} />
            ))}
          </span>
        </span>
      ),
    });
    return confirmed ? "confirmed" : "cancelled";
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
      // Место окна помнится до конца сеанса: операции правят одну за другой,
      // и отодвигать окно от списка на каждую — работа вместо работы.
      positionKey="transaction-form"
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
              // Разбивка между людьми есть только у расчётов: у покупки
              // второй стороны нет, и доли там означали бы неизвестно что.
              if (!SETTLEMENT_TYPES.includes(nextType)) setPeopleRows([]);
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
            {beforeOpening && (
              <p className="mt-1 text-xs text-danger">
                {t("transactions.form.beforeOpening", {
                  date: formatTransactionDate(beforeOpening, true),
                })}
              </p>
            )}
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
            {/* Один человек или несколько.

                Пока строк нет, человек называется обычным полем — так
                выглядит подавляющее большинство расчётов. «Разделить между
                людьми» превращает поле в список: долг вернули трое одним
                переводом, и в выписке банка это одна операция.

                Вид расчёта при этом один на всю операцию: трое, вернувшие
                долг, вернули именно долг. */}
            {peopleRows.length === 0 ? (
              <div>
                {/* «Кому» у исходящего и «От кого» у входящего: одно слово на
                    оба направления заставляло бы переводить подпись в уме. */}
                <Label htmlFor="counterparty">
                  {t(
                    form.type === "external_in"
                      ? "transactions.form.counterpartyFromLabel"
                      : "transactions.form.counterpartyLabel"
                  )}
                </Label>
                <DirectoryPicker
                  id="counterparty"
                  options={counterparties ?? []}
                  value={form.counterparty_id}
                  onChange={(value) => setForm((prev) => ({ ...prev, counterparty_id: value }))}
                  placeholder={t("transactions.form.selectCounterparty")}
                  onCreate={async (name) => (await createCounterparty.mutateAsync({ name })).id}
                />
                <button
                  type="button"
                  onClick={() =>
                    // Первая строка забирает уже выбранного человека и всю
                    // сумму: чаще всего делят именно её, и начинать с двух
                    // пустых строк значило бы заставить вводить заново.
                    setPeopleRows([
                      {
                        ...emptyPersonRow(),
                        counterparty_id: form.counterparty_id,
                        amount: form.amount,
                      },
                      emptyPersonRow(),
                    ])
                  }
                  className="mt-1.5 text-xs font-medium text-series-1 hover:underline"
                >
                  {t("transactions.form.splitBetweenPeople")}
                </button>
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label>{t("transactions.form.peopleLabel")}</Label>
                {peopleRows.map((row, index) => (
                  <div key={row.key} className="flex items-center gap-1.5">
                    {/* Обёрткой, а не классом: у DirectoryPicker своего
                        className нет, и ширину задаёт то, во что он
                        положен. */}
                    <span className="min-w-0 flex-1">
                    <DirectoryPicker
                      id={index === 0 ? "counterparty" : `counterparty-${row.key}`}
                      options={counterparties ?? []}
                      value={row.counterparty_id}
                      onChange={(value) =>
                        setPeopleRows((prev) =>
                          prev.map((item) =>
                            item.key === row.key ? { ...item, counterparty_id: value } : item
                          )
                        )
                      }
                      placeholder={t("transactions.form.selectCounterparty")}
                      onCreate={async (name) => (await createCounterparty.mutateAsync({ name })).id}
                    />
                    </span>
                    <Input
                      type="number"
                      step="0.01"
                      min="0.01"
                      className="w-28 shrink-0"
                      value={row.amount}
                      onChange={(event) =>
                        setPeopleRows((prev) =>
                          prev.map((item) =>
                            item.key === row.key ? { ...item, amount: event.target.value } : item
                          )
                        )
                      }
                    />
                    <button
                      type="button"
                      aria-label={t("transactions.form.peopleRemoveRow")}
                      onClick={() =>
                        setPeopleRows((prev) => prev.filter((item) => item.key !== row.key))
                      }
                      className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                    >
                      <X size={15} />
                    </button>
                  </div>
                ))}
                <div className="flex items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => setPeopleRows((prev) => [...prev, emptyPersonRow()])}
                    className="text-xs font-medium text-series-1 hover:underline"
                  >
                    {t("transactions.form.peopleAddRow")}
                  </button>
                  {/* Сколько ещё не разнесено. Та же подсказка, что у
                      разбивки по категориям: сумма обязана сойтись ровно, и
                      узнать об этом лучше здесь, чем из отказа сервера. */}
                  <p
                    className={`text-xs ${peopleRemainingCents === 0 ? "text-success" : "text-text-muted"}`}
                  >
                    {peopleRemainingCents > 0
                      ? t("transactions.form.splitRemainingLabel", {
                          amount: formatCurrency(peopleRemainingCents / 100),
                        })
                      : peopleRemainingCents < 0
                        ? t("transactions.form.splitOverAllocatedLabel", {
                            amount: formatCurrency(Math.abs(peopleRemainingCents) / 100),
                          })
                        : t("transactions.form.splitFullyAllocatedLabel")}
                  </p>
                </div>
              </div>
            )}

            <div>
              <LabelWithHelp htmlFor="settlement_kind" hintKey="transactions.form.settlementHint">
                {t("transactions.form.settlementKindLabel")}
              </LabelWithHelp>
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
            </div>

            {/* Чьи это деньги. Одного поля на транзит не хватает: в
                контрагенте стоит тот, с кем прошла операция, а деньги могут
                быть третьего — брат передал на покупки для мамы, и без
                второго поля сложить приход с расходом не по чему.

                Вопрос одинаковый в обе стороны, поэтому и подпись одна: у
                прихода «чьи деньги мне дали», у расхода «чьи деньги я
                передаю». Пустое поле значит «его» у прихода и «мои» у
                расхода — самый частый случай. */}
            {isTransit && (
              <div>
                {/* У исходящего транзита «От кого» — чьи деньги я передаю. У
                    входящего так назвать нельзя: «От кого» там уже стоит
                    выше, у контрагента, и две одинаковые подписи подряд
                    читались бы как один вопрос. */}
                <LabelWithHelp htmlFor="transit_party" hintKey="transactions.form.transitPartyHint">
                  {t(
                    form.type === "external_in"
                      ? "transactions.form.transitOwnerLabel"
                      : "transactions.form.transitFromLabel"
                  )}
                </LabelWithHelp>
                <DirectoryPicker
                  id="transit_party"
                  options={counterparties ?? []}
                  value={form.transit_party_id}
                  onChange={(value) => setForm((prev) => ({ ...prev, transit_party_id: value }))}
                  emptyLabel={t("transactions.form.transitPartyNone")}
                  placeholder={t("transactions.form.selectCounterparty")}
                  onCreate={async (name) => (await createCounterparty.mutateAsync({ name })).id}
                />
              </div>
            )}

            {/* Категория у движения с человеком. Раньше её здесь не было
                вовсе, и покупку на чужие деньги нельзя было ни на что
                повесить — оставалось писать «продукты» в описание.
                Необязательна: у «занял до зарплаты» ей взяться неоткуда.

                В траты и в круг категорий такая запись по-прежнему не
                попадает — она и не трата: деньги были не свои. Категория
                здесь — чтобы найти покупку потом и увидеть её в списке
                рядом с остальными продуктовыми. */}
            <div>
              <LabelWithHelp htmlFor="settlement-category" hintKey="transactions.form.settlementCategoryHint">
                {t("transactions.form.categoryLabel")}
              </LabelWithHelp>
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

            {/* Вторая сумма — только между разными валютами.

                Вывести её из курса ЦБ нельзя: банк меняет по своему курсу и
                берёт свою комиссию, и сколько дошло — знает только выписка.
                Поэтому оба числа переписываются оттуда, а приложение ничего
                не додумывает: разница между ними и есть цена перевода. */}
            {crossCurrencyTransfer && (
              <div className="mt-3">
                <Label htmlFor="transfer_amount">
                  {t("transactions.form.transferAmountLabel", {
                    currency: destinationAccount?.currency ?? "",
                  })}
                </Label>
                <Input
                  id="transfer_amount"
                  type="number"
                  step="0.01"
                  min="0.01"
                  required
                  value={form.transfer_amount}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, transfer_amount: event.target.value }))
                  }
                />
                <p className="mt-1 text-xs text-text-muted">
                  {t("transactions.form.transferAmountHint")}
                </p>
              </div>
            )}
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
        {/* Значок вне <label>: внутри щелчок по нему заодно переключал бы
            саму галочку, и объяснение её и включало. */}
        <div className="flex items-center gap-1.5">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_excluded}
              onChange={(event) => setForm((prev) => ({ ...prev, is_excluded: event.target.checked }))}
              className="h-3.5 w-3.5 accent-text-primary"
            />
            <span>{t("transactions.form.excludedLabel")}</span>
          </label>
          <HelpBadge hintKey="transactions.form.excludedHint" />
        </div>

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
