import { useState, type ReactNode } from "react";
import { SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Label, Select } from "@/components/ui/Input";
import { CategoryPicker } from "@/components/categories/CategoryPicker";
import { useAccounts } from "@/hooks/useAccounts";
import { useCategories } from "@/hooks/useCategories";
import { useBanks, useCounterparties, useParticipants, useStores } from "@/hooks/useDirectories";
import { useTags } from "@/hooks/useTags";
import { useTranslation } from "@/lib/i18n";
import type { TransactionFilters } from "@/api/transactions";
import type { TransactionType } from "@/types";

/** «Участник не указан» — не номер: у отсутствия номера нет, и подставить
 *  сюда ноль или минус единицу значило бы однажды совпасть с настоящим. */
export const NO_PARTICIPANT = "none";

/** Отбор списка операций — всё, кроме периода, поиска и сортировки: те
 *  остаются на виду, потому что ими пользуются в каждом заходе. */
export interface TransactionFilterValues {
  type: TransactionType | "";
  counterpartyId: string;
  accountId: string;
  bankId: string;
  categoryId: string;
  storeId: string;
  tagId: string;
  /** Номер участника, NO_PARTICIPANT или пусто. */
  participantId: string;
  /** Спрятать записи «не учитывать». По умолчанию они видны наравне с
   *  остальными: их и заводят ради того, чтобы о покупке помнить. */
  hideExcluded: boolean;
}

export const EMPTY_FILTERS: TransactionFilterValues = {
  type: "",
  counterpartyId: "",
  accountId: "",
  bankId: "",
  categoryId: "",
  storeId: "",
  tagId: "",
  participantId: "",
  hideExcluded: false,
};

/** Человек, с которым шёл расчёт, спрашивается только у расчётов: у покупки
 *  в магазине контрагента нет, и пустой отбор там обещал бы то, чего не
 *  существует. */
function isSettlement(type: TransactionType | ""): boolean {
  return type === "external_out" || type === "external_in";
}

/** Сколько отборов сейчас сужают список — число на кнопке. Без него
 *  свёрнутая панель прячет причину, по которой строк оказалось мало. */
export function activeFilterCount(value: TransactionFilterValues): number {
  const chosen = [
    value.type,
    isSettlement(value.type) ? value.counterpartyId : "",
    value.accountId,
    value.bankId,
    value.categoryId,
    value.storeId,
    value.tagId,
    value.participantId,
  ].filter(Boolean).length;
  return chosen + (value.hideExcluded ? 1 : 0);
}

/**
 * Отбор в том виде, в котором его понимает сервер.
 *
 * Здесь же, рядом с самими значениями: страница не должна знать, что
 * «участник не указан» уходит отдельным признаком, а «спрятать не
 * учитываемые» — обратным по смыслу include_excluded.
 */
export function filterQuery(value: TransactionFilterValues): TransactionFilters {
  return {
    type: value.type || undefined,
    // Только когда поле видно. Отбор, который не показан, но продолжает
    // сужать список, читается как поломанный период: строк мало, а почему —
    // не видно нигде.
    counterparty_id:
      isSettlement(value.type) && value.counterpartyId ? Number(value.counterpartyId) : undefined,
    account_id: value.accountId ? Number(value.accountId) : undefined,
    bank_id: value.bankId ? Number(value.bankId) : undefined,
    category_id: value.categoryId ? Number(value.categoryId) : undefined,
    store_id: value.storeId ? Number(value.storeId) : undefined,
    tag_id: value.tagId ? Number(value.tagId) : undefined,
    participant_id:
      value.participantId && value.participantId !== NO_PARTICIPANT
        ? Number(value.participantId)
        : undefined,
    no_participant: value.participantId === NO_PARTICIPANT ? true : undefined,
    include_excluded: value.hideExcluded ? false : undefined,
  };
}

/**
 * Панель отборов: кнопка с числом активных и раскрывающийся набор полей.
 *
 * Отборов стало больше десяти, и в строку они не встают: на телефоне такая
 * строка занимала весь экран, а на ПК отнимала у списка три строки в каждом
 * заходе, хотя меняют их редко. Поэтому в строке остаются период, поиск и
 * сортировка, а остальное — за кнопкой.
 *
 * Панель раскрыта сразу, если отборы уже стоят: иначе непонятно, почему
 * список короткий.
 *
 * Поля, для которых справочник пуст, не показываются вовсе: выбор из
 * ничего — обещание отбора, которого нет.
 */
export function TransactionFiltersPanel({
  value,
  onChange,
  trailing,
}: {
  value: TransactionFilterValues;
  onChange: (next: TransactionFilterValues) => void;
  /** Что стоит в той же строке справа — сортировка. */
  trailing?: ReactNode;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(() => activeFilterCount(value) > 0);
  const { data: accounts } = useAccounts(false);
  const { data: banks } = useBanks();
  const { data: categories } = useCategories();
  const { data: counterparties } = useCounterparties();
  const { data: participants } = useParticipants();
  const { data: stores } = useStores();
  const { data: tags } = useTags();

  const active = activeFilterCount(value);
  const set = (patch: Partial<TransactionFilterValues>) => onChange({ ...value, ...patch });

  // Категории расходов и доходов в одном списке, разделённые заголовками, и
  // подкатегория стоит под своим родителем с отступом: голое «Сладкое»
  // рядом с корневыми читалось бы как ещё одна корневая.
  const filterCategories = (categories ?? [])
    .filter((category) => category.kind === "expense" || category.kind === "income")
    .map((category) => ({
      ...category,
      group: t(category.kind === "expense" ? "reports.expenseGroup" : "reports.incomeGroup"),
    }));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant={active > 0 ? "primary" : "secondary"} onClick={() => setOpen(!open)}>
          <SlidersHorizontal size={15} />
          {t("transactions.filtersButton")}
          {active > 0 && <span className="tabular-nums">· {active}</span>}
        </Button>
        {active > 0 && (
          <Button variant="ghost" onClick={() => onChange(EMPTY_FILTERS)}>
            {t("transactions.filtersReset")}
          </Button>
        )}
        {trailing && <span className="ml-auto">{trailing}</span>}
      </div>

      {open && (
        <div className="grid gap-3 rounded-lg border border-border bg-surface-1 p-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <Label htmlFor="filter-type">{t("transactions.form.typeLabel")}</Label>
            <Select
              id="filter-type"
              value={value.type}
              onChange={(event) => {
                const nextType = event.target.value as TransactionType | "";
                // Уходя с расчётов, снимаем и человека: иначе он остался бы
                // висеть и сузил бы следующий отбор молча.
                set({ type: nextType, counterpartyId: isSettlement(nextType) ? value.counterpartyId : "" });
              }}
            >
              <option value="">{t("transactions.allTypes")}</option>
              <option value="expense">{t("transactions.expense")}</option>
              <option value="income">{t("transactions.income")}</option>
              <option value="transfer">{t("transactions.transfer")}</option>
              {/* Во множественном числе, в отличие от формы: отбор берёт все
                  такие операции, а в форме заводится одна. */}
              <option value="external_out">{t("transactions.filterExternalOut")}</option>
              <option value="external_in">{t("transactions.filterExternalIn")}</option>
            </Select>
          </div>

          {/* Человек — сразу за видом операции: он уточняет именно его. */}
          {isSettlement(value.type) && (
            <div>
              <Label htmlFor="filter-counterparty">{t("transactions.filterPersonLabel")}</Label>
              <Select
                id="filter-counterparty"
                value={value.counterpartyId}
                onChange={(event) => set({ counterpartyId: event.target.value })}
              >
                <option value="">{t("transactions.allCounterparties")}</option>
                {(counterparties ?? []).map((counterparty) => (
                  <option key={counterparty.id} value={counterparty.id}>
                    {counterparty.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          <div>
            <Label htmlFor="filter-account">{t("transactions.form.accountLabel")}</Label>
            <Select
              id="filter-account"
              value={value.accountId}
              onChange={(event) => set({ accountId: event.target.value })}
            >
              <option value="">{t("transactions.allAccounts")}</option>
              {(accounts ?? []).map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </Select>
          </div>

          {/* Банк — все его счета сразу: у одного банка бывает и карта, и
              рассрочка, и сверять выписку удобнее целиком. */}
          {banks && banks.length > 0 && (
            <div>
              <Label htmlFor="filter-bank">{t("account.form.bankLabel")}</Label>
              <Select
                id="filter-bank"
                value={value.bankId}
                onChange={(event) => set({ bankId: event.target.value })}
              >
                <option value="">{t("transactions.allBanks")}</option>
                {banks.map((bank) => (
                  <option key={bank.id} value={bank.id}>
                    {bank.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          <div>
            <Label htmlFor="filter-category">{t("transactions.form.categoryLabel")}</Label>
            <CategoryPicker
              id="filter-category"
              categories={filterCategories}
              value={value.categoryId}
              onChange={(next) => set({ categoryId: next })}
              placeholder={t("transactions.allCategories")}
              emptyLabel={t("transactions.allCategories")}
            />
          </div>

          {/* Участник — и «не указан» отдельной строкой: так находятся
              операции, где его забыли поставить. */}
          {participants && participants.length > 0 && (
            <div>
              <Label htmlFor="filter-participant">{t("transactions.form.participantLabel")}</Label>
              <Select
                id="filter-participant"
                value={value.participantId}
                onChange={(event) => set({ participantId: event.target.value })}
              >
                <option value="">{t("transactions.allParticipants")}</option>
                <option value={NO_PARTICIPANT}>{t("transactions.participantMissing")}</option>
                {participants.map((participant) => (
                  <option key={participant.id} value={participant.id}>
                    {participant.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {stores && stores.length > 0 && (
            <div>
              <Label htmlFor="filter-store">{t("transactions.form.storeLabel")}</Label>
              <Select
                id="filter-store"
                value={value.storeId}
                onChange={(event) => set({ storeId: event.target.value })}
              >
                <option value="">{t("transactions.allStores")}</option>
                {stores.map((store) => (
                  <option key={store.id} value={store.id}>
                    {store.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {tags && tags.length > 0 && (
            <div>
              <Label htmlFor="filter-tag">{t("transactions.form.tagsLabel")}</Label>
              <Select
                id="filter-tag"
                value={value.tagId}
                onChange={(event) => set({ tagId: event.target.value })}
              >
                <option value="">{t("transactions.allTags")}</option>
                {tags.map((tag) => (
                  <option key={tag.id} value={tag.id}>
                    {tag.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {/* Галочка, а не выбор из двух: «показывать» — обычное положение
              дел, и называть его вслух незачем.

              Строка той же высоты, что у полей рядом, и прижата к низу
              ячейки: у соседей сверху стоит подпись, и без этого галочка
              оказывалась выше их полей. Раньше высота набиралась отступами
              снизу — у строки свой, у самой галочки свой, — и получалась
              лесенка: галочка, её подпись и соседнее поле стояли каждый на
              своём уровне. Высота и выравнивание по центру решают это одни,
              без подгонки на пиксели. */}
          <label className="flex h-9 items-center gap-2 self-end text-sm sm:col-span-2 lg:col-span-1">
            <input
              type="checkbox"
              checked={value.hideExcluded}
              onChange={(event) => set({ hideExcluded: event.target.checked })}
              className="h-3.5 w-3.5 accent-text-primary"
            />
            <span>{t("transactions.hideExcluded")}</span>
          </label>
        </div>
      )}
    </div>
  );
}
