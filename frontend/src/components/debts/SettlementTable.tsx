import { useTranslation } from "@/lib/i18n";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import type { Settlement } from "@/types";

interface SettlementTableProps {
  items: Settlement[];
}

/**
 * Расчёты с людьми одной таблицей.
 *
 * Порядок задаётся бэкендом и не переставляется здесь: сверху те, кто должен
 * больше всего, ниже нулевые, в самом низу те, кому должны вы. Список читается
 * как ответ на вопрос «где мои деньги», и самая крупная строка обязана быть
 * первой.
 *
 * Оборот и долг стоят рядом, но разделены визуально: приглушённые колонки
 * слева — сколько всего прошло через человека, яркая справа — сколько осталось
 * вернуть. Смешивать их нельзя: жена, передавшая за четыре года полмиллиона
 * на продукты, ничего не должна.
 */
export function SettlementTable({ items }: SettlementTableProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("debts.noPeople")}</p>;
  }

  return (
    <>
      {/* Десктоп: полная таблица с оборотом. */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-muted">
              <th className="py-2 pr-3 font-medium">{t("debts.people")}</th>
              <th className="py-2 px-3 text-right font-medium">{t("debts.received")}</th>
              <th className="py-2 px-3 text-right font-medium">{t("debts.given")}</th>
              <th className="py-2 px-3 text-right font-medium">{t("debts.operations")}</th>
              <th className="py-2 px-3 text-right font-medium">{t("debts.lastOperation")}</th>
              <th className="py-2 pl-3 text-right font-medium">{t("debts.net")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.counterparty_id} className="border-b border-border/50 last:border-0">
                <td className="py-2.5 pr-3 font-medium">{item.name}</td>
                <td className="py-2.5 px-3 text-right tabular-nums text-text-muted">
                  {formatCurrency(item.received)}
                </td>
                <td className="py-2.5 px-3 text-right tabular-nums text-text-muted">
                  {formatCurrency(item.given)}
                </td>
                <td className="py-2.5 px-3 text-right tabular-nums text-text-muted">{item.operations}</td>
                <td className="py-2.5 px-3 text-right tabular-nums text-text-muted">
                  {item.last_date ? formatTransactionDate(item.last_date, true) : "—"}
                </td>
                <td className="py-2.5 pl-3 text-right">
                  <BalanceCell balance={item.balance} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Мобильный: оборот убран в подпись — на узком экране шесть колонок
          превращаются в кашу, а вопрос «кто сколько должен» остаётся тем же. */}
      <ul className="space-y-2 md:hidden">
        {items.map((item) => (
          <li
            key={item.counterparty_id}
            className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5"
          >
            <div className="min-w-0">
              <p className="truncate font-medium">{item.name}</p>
              <p className="mt-0.5 text-xs text-text-muted">
                {t("debts.turnover")}: {formatCurrency(item.received)} / {formatCurrency(item.given)}
              </p>
            </div>
            <BalanceCell balance={item.balance} />
          </li>
        ))}
      </ul>
    </>
  );
}

/**
 * Остаток долга. Ноль намеренно не красится ни в зелёный, ни в красный и
 * подписывается словом: «рассчитались» — это результат, а не отсутствие
 * данных, и цифра 0,00 ₽ читалась бы как пустая строка.
 */
function BalanceCell({ balance }: { balance: string }) {
  const { t } = useTranslation();
  const value = Number(balance);

  if (value === 0) {
    return <span className="text-xs text-text-muted">{t("debts.settled")}</span>;
  }

  return (
    <span
      className={`whitespace-nowrap font-semibold tabular-nums ${
        value > 0 ? "text-success" : "text-danger"
      }`}
    >
      {formatCurrency(Math.abs(value))}
    </span>
  );
}
