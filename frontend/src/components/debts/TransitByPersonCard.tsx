import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { PillSelector } from "@/components/layout/PillSelector";
import { Combobox } from "@/components/ui/Combobox";
import { useTransitByPerson } from "@/hooks/useDebts";
import { useTransactionYears } from "@/hooks/useTransactions";
import { formatCurrency, getMonthLabels } from "@/lib/format";
import { getLanguage, useTranslation } from "@/lib/i18n";

/**
 * Транзит, разложенный по людям.
 *
 * Отвечает на вопрос «сошлось ли с человеком»: сколько он передал на
 * покупки и сколько на них ушло. Долгом это не становится — недодавший на
 * продукты ничего не обязан возвращать, пока об этом не договорились, — но
 * разница видна, и видно, с кем именно.
 *
 * Складывается по тому, ДЛЯ КОГО шли деньги. Источник, передавший на
 * покупки для кого-то третьего, в списке не появляется: он не сторона.
 *
 * Внизу вкладки, а не вверху: у большинства транзитов нет вовсе, а долги и
 * кредиты есть почти у всех.
 */
export function TransitByPersonCard() {
  const { t } = useTranslation();
  const { data: years } = useTransactionYears();
  // «Всё время» по умолчанию: вопрос «с кем не сошлось» задают вообще, а не
  // про конкретный месяц. Месяц — уточнение, и им пользуются реже.
  const [year, setYear] = useState<number | "">("");
  const [month, setMonth] = useState<number | "">("");
  const { data: rows } = useTransitByPerson(
    year === "" ? undefined : year,
    year === "" || month === "" ? undefined : month
  );

  if (!rows || rows.length === 0) {
    // Пустая карточка объясняла бы понятие, которым человек не пользуется.
    // Но если фильтр сузили до пустоты — карточку оставляем: исчезнувший
    // на смене месяца блок читается как поломка.
    if (year === "" && month === "") return null;
  }

  const months = getMonthLabels(getLanguage());
  const yearOptions = [
    { value: "", label: t("debts.transitAllTime") },
    ...(years ?? []).map((value) => ({ value: String(value), label: String(value) })),
  ];

  return (
    <Card>
      <CardHeader className="items-start">
        <CardTitle className="flex items-center gap-1.5">
          {t("debts.transitByPerson")}
          <HelpBadge hintKey="help.transitByPerson" />
        </CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          <Combobox
            className="w-36"
            options={yearOptions}
            value={year === "" ? "" : String(year)}
            onChange={(value) => {
              setYear(value === "" ? "" : Number(value));
              if (value === "") setMonth("");
            }}
            placeholder={t("debts.transitAllTime")}
          />
          {/* Месяц только при выбранном годе: «март» без года — это про
              какой март? */}
          {year !== "" && (
            <PillSelector
              options={[
                { value: "", label: t("debts.transitWholeYear") },
                ...months.map((label, index) => ({ value: String(index + 1), label: label.slice(0, 3) })),
              ]}
              value={month === "" ? "" : String(month)}
              onChange={(value) => setMonth(value === "" ? "" : Number(value))}
            />
          )}
        </div>
      </CardHeader>
      <CardContent>
        {!rows || rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-muted">{t("debts.transitEmpty")}</p>
        ) : (
          <ul className="divide-y divide-gridline">
            {rows.map((row) => {
              const balance = Number(row.balance);
              return (
                <li key={row.counterparty_id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{row.name}</span>
                    <span className="block truncate text-xs text-text-muted">
                      {t("debts.transitFlow", {
                        received: formatCurrency(row.received),
                        spent: formatCurrency(row.spent),
                      })}
                    </span>
                  </span>
                  {/* Ноль подписывается словом: цифра 0,00 ₽ в этой колонке
                      читается как «данных нет», а это результат. */}
                  {balance === 0 ? (
                    <span className="shrink-0 text-xs text-text-muted">{t("debts.transitEven")}</span>
                  ) : (
                    <span
                      className={`shrink-0 whitespace-nowrap font-semibold tabular-nums ${
                        balance > 0 ? "text-success" : "text-danger"
                      }`}
                    >
                      {formatCurrency(Math.abs(balance))}
                      <span className="block text-right text-xs font-normal text-text-muted">
                        {t(balance > 0 ? "debts.transitLeftOver" : "debts.transitShort")}
                      </span>
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
