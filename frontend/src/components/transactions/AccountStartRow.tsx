import { formatCurrency, formatTransactionDate } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";

/** Начальный остаток счёта: сумма, лежавшая на нём до первой записи. */
export interface AccountStart {
  /** День, с которого счёт считается открытым. Пусто — «до начала учёта». */
  date: string | null;
  amount: string;
  currency: string;
}

/**
 * Черта под списком операций: здесь счёт начался, и вот с какой суммой.
 *
 * Строкой списка начальный остаток быть не может — у него нет ни категории,
 * ни направления, он не операция. Но и молчать о нём нельзя: список
 * заканчивается, а остаток на счёте больше суммы операций, и объяснить
 * разницу нечем.
 *
 * Стоит под самой старой операцией, потому что список идёт от новых к старым:
 * начало счёта — это его низ. Показывается только когда видно начало истории
 * счёта, то есть на последней странице или в конце ленты.
 */
export function AccountStartLabel({ start }: { start: AccountStart }) {
  const { t } = useTranslation();
  return (
    <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
      <span className="text-xs font-medium uppercase tracking-wide text-text-secondary">
        {start.date
          ? t("transactions.accountStartOn", { date: formatTransactionDate(start.date, true) })
          : t("transactions.accountStart")}
      </span>
      <span className="text-xs font-medium tabular-nums text-text-primary">
        {formatCurrency(start.amount, start.currency)}
      </span>
    </span>
  );
}
