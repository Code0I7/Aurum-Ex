import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import { formatWorkCost, rateForDate } from "@/lib/hours";
import { useHourlyRates } from "@/hooks/usePlans";
import type { LargestExpense } from "@/types";

/**
 * Самые крупные траты периода.
 *
 * Объясняют, куда ушли деньги, лучше любой диаграммы: круг из восьми долей
 * отвечает «на что вообще», а этот список — «из-за чего именно в этом
 * месяце».
 */
export function LargestExpensesCard({
  items,
  className,
}: {
  items: LargestExpense[];
  /** Высота задаётся снаружи: в сетке обзора карточка тянется до низа
   *  своей строки, иначе рядом с соседкой у неё разный нижний край. */
  className?: string;
}) {
  const { t } = useTranslation();
  const { data: rates } = useHourlyRates();

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{t("dashboard.largestTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-muted">{t("dashboard.largestEmpty")}</p>
        ) : (
          <ul className="divide-y divide-gridline">
            {items.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0">
                  <span className="block truncate text-sm">{item.description}</span>
                  <span className="block truncate text-xs text-text-muted">
                    {formatTransactionDate(item.date, true)}
                    {item.category_name && ` · ${item.category_name}`}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block text-sm font-medium tabular-nums">
                    {formatCurrency(item.amount)}
                  </span>
                  {/* Та же сумма во времени. Ради этого список крупнейших
                      трат и стоит рядом с заработком за час: «монитор — это
                      четыре дня» объясняет месяц лучше любой диаграммы. */}
                  {(() => {
                    const cost = formatWorkCost(item.amount, rateForDate(rates, item.date));
                    return cost === null ? null : (
                      <span className="block text-xs tabular-nums text-text-muted">≈ {cost}</span>
                    );
                  })()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
