import { useTranslation } from "@/lib/i18n";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import type { Settlement, TransitPerson } from "@/types";

interface SettlementTableProps {
  items: Settlement[];
  /**
   * Транзит по людям за всё время — отдельной колонкой. Вопрос «сошлось ли
   * с ним» задают о том же человеке и в тот же момент, что и «сколько он
   * должен», и гонять глазами между двумя блоками незачем.
   *
   * Долгом транзит не становится, поэтому и не встаёт в колонку остатка:
   * недодавший на продукты ничего не обязан возвращать.
   */
  transit?: TransitPerson[];
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
export function SettlementTable({ items, transit = [] }: SettlementTableProps) {
  const { t } = useTranslation();
  const transitByPerson = new Map(transit.map((row) => [row.counterparty_id, row]));
  // Колонка появляется, только если транзиты вообще были: у большинства их
  // нет, и столбец из прочерков объяснял бы понятие, которым не пользуются.
  const showTransit = transit.length > 0;

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
              {showTransit && (
                <th className="py-2 px-3 text-right font-medium">{t("debts.transitBalance")}</th>
              )}
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
                {showTransit && (
                  <td className="py-2.5 px-3 text-right text-sm">
                    <TransitCell row={transitByPerson.get(item.counterparty_id)} />
                  </td>
                )}
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
              {/* Колонок на узком экране нет, поэтому транзит становится
                  подписанной строкой — той же, что заголовок колонки. */}
              {showTransit && (
                <p className="mt-0.5 text-xs text-text-muted">
                  {t("debts.transitBalance")}:{" "}
                  <TransitCell row={transitByPerson.get(item.counterparty_id)} />
                </p>
              )}
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

/**
 * Баланс транзита с человеком: плюс — его деньги ещё лежат у вас, минус —
 * вы вложили за него своих.
 *
 * Чужое, прошедшее насквозь, сюда не попадает. Брат передал 4 500 на
 * покупки для мамы, я отдал маме эти 4 500 и ещё 370 своих: у брата ноль —
 * его деньги дошли, у мамы −370. «Маме 4 870» не появится: три четверти
 * этой суммы были не мои.
 *
 * Знак не прячется под цвет, в отличие от соседней колонки остатка: минус
 * значит «вложил своих», и читается он как минус, а не сверяется по цвету.
 *
 * Долгом ни то, ни другое не становится и в колонку остатка не встаёт:
 * недодавший на продукты ничего не обязан возвращать, пока об этом не
 * договорились.
 */
function TransitCell({ row }: { row?: TransitPerson }) {
  const { t } = useTranslation();
  // Прочерк, а не ноль: ноль здесь означает «сошлось», то есть что транзит
  // был и разошёлся в ноль, — а у этого человека его не было вовсе.
  if (!row) return <span className="text-text-muted">—</span>;

  const balance = Number(row.balance);
  if (balance === 0) {
    return <span className="text-xs text-text-muted">{t("debts.transitEven")}</span>;
  }

  return (
    <span
      className={`whitespace-nowrap font-semibold tabular-nums ${
        balance > 0 ? "text-success" : "text-danger"
      }`}
    >
      {formatCurrency(balance)}
    </span>
  );
}
