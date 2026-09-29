import { Pencil } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import type { CreditTerms } from "@/types";

interface CreditListProps {
  items: CreditTerms[];
  onEdit: (item: CreditTerms) => void;
}

/**
 * Кредиты карточками, а не строками таблицы.
 *
 * У кредита семь разнородных характеристик — долг, лимит, ставка, льготный
 * период, день платежа, минимальный платёж, оценка процентов, — и половина
 * обычно не заполнена. В таблице это дало бы поле пустых прочерков; карточка
 * показывает только то, что задано.
 *
 * Порядок приходит с сервера: сначала самый большой долг. Список отвечает на
 * вопрос «что гасить в первую очередь».
 */
export function CreditList({ items, onEdit }: CreditListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("debts.noCredits")}</p>;
  }

  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {items.map((item) => (
        <li key={item.account_id} className="rounded-lg border border-border p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-medium">{item.account_name}</p>
              <p className="mt-1 text-xl font-semibold tabular-nums text-danger">
                {formatCurrency(item.debt, item.account_currency)}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onEdit(item)}
              className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
              aria-label={t("debts.editTerms")}
            >
              <Pencil size={15} />
            </button>
          </div>

          {/* Полоса использования лимита. Показывается только когда лимит
              задан: у обычного кредита его нет, и пустая полоса врала бы. */}
          {item.credit_limit !== null && item.used_percent !== null && (
            <div className="mt-3">
              <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                <div
                  // Перебор лимита банк иногда пропускает. Полоса упирается в
                  // 100%, но цвет меняется — иначе перебор выглядел бы просто
                  // как «полный лимит».
                  className={`h-full rounded-full ${item.used_percent > 100 ? "bg-danger" : "bg-text-secondary"}`}
                  style={{ width: `${Math.min(item.used_percent, 100)}%` }}
                />
              </div>
              <p className="mt-1.5 flex justify-between text-xs text-text-muted">
                <span>
                  {t("debts.available")}:{" "}
                  {formatCurrency(item.available ?? "0", item.account_currency)}
                </span>
                <span className="tabular-nums">
                  {item.used_percent}% {t("debts.limit").toLowerCase()}
                </span>
              </p>
            </div>
          )}

          <dl className="mt-3 space-y-1 text-xs">
            <Row label={t("debts.rate")} value={item.annual_rate_percent ? `${Number(item.annual_rate_percent)}%` : null} />
            <Row
              label={t("debts.gracePeriod")}
              value={item.grace_days ? t("debts.graceDays", { days: item.grace_days }) : null}
            />
            <Row
              label={t("debts.paymentDay")}
              value={item.payment_day ? t("debts.paymentDayValue", { day: item.payment_day }) : null}
            />
            {/* Минимальный платёж — то, что реально придётся заплатить в
                этом месяце, а рядом правило, по которому он вышел: без
                правила число нечем проверить, без числа правило нечем
                применить. */}
            <Row
              label={t("debts.minimumPayment")}
              value={
                item.minimum_payment_due
                  ? formatCurrency(item.minimum_payment_due, item.account_currency)
                  : item.minimum_payment
                    ? formatCurrency(item.minimum_payment, item.account_currency)
                    : null
              }
            />
            <Row
              label={t("debts.minimumRule")}
              value={
                item.minimum_payment_percent
                  ? t("debts.minimumRuleValue", {
                      percent: Number(item.minimum_payment_percent),
                      floor: item.minimum_payment
                        ? formatCurrency(item.minimum_payment, item.account_currency)
                        : "—",
                    })
                  : null
              }
              muted
            />
            <Row
              label={t("debts.monthlyInterest")}
              value={
                item.estimated_monthly_interest
                  ? `≈ ${formatCurrency(item.estimated_monthly_interest, item.account_currency)}`
                  : null
              }
              // Знак ≈ стоит не для красоты: это оценка, а не банковское число.
              muted
            />
            <Row
              label={t("debts.closesOn")}
              value={item.closes_on ? formatTransactionDate(item.closes_on, true) : null}
            />
          </dl>

          {/* Матрица ставок: снятие наличных стоит вдвое дороже покупок, и
              вспоминают об этом обычно уже после снятия. */}
          {item.rates.length > 0 && (
            <ul className="mt-2 space-y-0.5 border-t border-border pt-2 text-xs">
              {item.rates.map((rate) => (
                <li key={rate.id} className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 truncate text-text-muted">
                    {rate.name}
                    {rate.condition ? ` · ${rate.condition}` : ""}
                  </span>
                  <span className="shrink-0 tabular-nums">{Number(rate.percent)}%</span>
                </li>
              ))}
            </ul>
          )}

          {/* Заметка в несколько строк: платы, бесплатные лимиты, неустойка.
              whitespace-pre-line — чтобы переносы, которые человек поставил
              сам, остались переносами. */}
          {item.notes && (
            <p className="mt-2 whitespace-pre-line text-xs text-text-muted">{item.notes}</p>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Строка «характеристика — значение». Незаполненная не выводится вовсе:
 *  прочерк занимает место и ничего не сообщает. */
function Row({ label, value, muted }: { label: string; value: string | null; muted?: boolean }) {
  if (!value) return null;
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-text-muted">{label}</dt>
      <dd className={`tabular-nums ${muted ? "text-text-muted" : "text-text-secondary"}`}>{value}</dd>
    </div>
  );
}
