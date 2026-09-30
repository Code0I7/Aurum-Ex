import { useState } from "react";
import { ChartBar, ChartPie, SquareDivide } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { CategoryBreakdownModal } from "@/components/categories/CategoryBreakdownModal";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { CategoryBreakdownItem } from "@/types";

/** Каким видом показывать разбивку. Полосы по умолчанию: круг отвечает
 *  только на «какая доля у крупнейшей», а список с полосами — ещё и на
 *  «насколько одна статья больше другой». */
type BreakdownView = "bars" | "donut";

interface CategoryBreakdownCardProps {
  title: string;
  /** Что сказать, когда за период нет ни одной операции этого вида. */
  emptyLabel: string;
  items: CategoryBreakdownItem[];
  /** Под каким именем запоминать выбранный вид. Своё у доходов и своё у
   *  расходов: карточки стоят рядом, но это два разных виджета, и
   *  переключать оба разом человек не просил. */
  viewKey: string;
  /** Высота задаётся снаружи: в сетке обзора карточка тянется до низа
   *  своей строки, иначе рядом с соседкой у неё разный нижний край. */
  className?: string;
}

function DonutTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: CategoryBreakdownItem }>;
}) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return (
    <ChartTooltipBox>
      <p className="font-medium text-text-primary">{translateCategoryName(item.name)}</p>
      <p className="text-text-secondary">
        {formatCurrency(item.amount)} · {item.percent.toFixed(1)}%
      </p>
    </ChartTooltipBox>
  );
}

/** Условный номер для доли «Прочее»: у неё нет своей категории, а окну
 *  разбивки номер нужен, чтобы отличить «прямые траты в самой категории»
 *  от подкатегорий. Ни одна настоящая категория с ним не совпадёт. */
const OTHER_SLICE_ID = -1;

/**
 * Разбивка расходов или доходов по категориям: круг сверху, список под ним.
 *
 * Одна карточка на оба вида, а не две копии. Расходы и доходы стоят на
 * обзоре рядом и обязаны выглядеть и считаться одинаково — две копии
 * разошлись бы при первой же правке одной из них.
 *
 * Круг над списком, а не слева от него. Карточка теперь в половину прежней
 * ширины, и рядом с кругом списку не оставалось бы места ни на название,
 * ни на сумму.
 *
 * Показываются семь крупнейших категорий и доля «Прочее». Остальные не
 * пропадают: «Прочее» открывается тем же окном, что и подкатегории, — со
 * списком того, что в неё свёрнуто.
 */
export function CategoryBreakdownCard({
  title,
  emptyLabel,
  items,
  viewKey,
  className,
}: CategoryBreakdownCardProps) {
  const { t } = useTranslation();
  // Вид переживает перезагрузку: это настройка, а не место, где человек
  // сейчас находится.
  const [view, setView] = useLocalStorageState<BreakdownView>(
    `aurum:breakdown-view-${viewKey}`,
    "bars",
  );
  // Разбивка — в окне, а не раскрытием в строке: категория с десятком
  // подкатегорий иначе растянула бы карточку и сломала бы ровный край с
  // соседними.
  const [breakdownItem, setBreakdownItem] = useState<CategoryBreakdownItem | null>(null);
  const hasData = items.length > 0;
  // Recharts нужна числовая величина, а суммы с сервера приходят строками.
  const chartData = items.map((item) => ({ ...item, amount: Number(item.amount) }));
  // Длина полосы — доля от крупнейшей статьи, а не от общей суммы. Долю от
  // суммы показывает круг; полосы нужны для другого вопроса — насколько
  // одна статья больше другой, — и от общей суммы десяток статей по три
  // процента выглядел бы десятком одинаковых чёрточек.
  const largest = chartData.reduce((top, item) => Math.max(top, item.amount), 0);

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {/* Значок показывает, куда переключит, а не что сейчас: кнопка
            отвечает на «что будет, если нажать». Пропадает без данных —
            переключать нечего. */}
        {hasData && (
          <button
            type="button"
            onClick={() => setView(view === "bars" ? "donut" : "bars")}
            title={t(view === "bars" ? "dashboard.breakdownAsDonut" : "dashboard.breakdownAsBars")}
            aria-label={t(view === "bars" ? "dashboard.breakdownAsDonut" : "dashboard.breakdownAsBars")}
            className="-m-1 shrink-0 rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary"
          >
            {view === "bars" ? <ChartPie size={15} /> : <ChartBar size={15} />}
          </button>
        )}
      </CardHeader>
      <CardContent>
        {!hasData ? (
          <p className="py-10 text-center text-sm text-text-muted">{emptyLabel}</p>
        ) : (
          <div className="chart-palette flex flex-col items-center gap-4">
            {view === "donut" && (
            <div className="h-40 w-40 shrink-0 sm:h-44 sm:w-44">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={chartData}
                    dataKey="amount"
                    nameKey="name"
                    innerRadius="62%"
                    outerRadius="100%"
                    paddingAngle={2}
                    stroke="var(--surface-1)"
                    strokeWidth={2}
                    isAnimationActive={false}
                  >
                    {items.map((item) => (
                      <Cell key={item.category_id ?? "other"} fill={item.color} />
                    ))}
                  </Pie>
                  <Tooltip isAnimationActive={false} content={<DonutTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            )}

            <ul className="w-full min-w-0 divide-y divide-gridline">
              {items.map((item) => {
                const Icon = getCategoryIcon(item.icon);
                const hasChildren = item.children.length > 0;
                return (
                  <li key={item.category_id ?? "other"} className="py-2 first:pt-0 last:pb-0">
                    <div className="flex items-center gap-2">
                    {/* Место под кнопку есть у каждой строки, даже без неё:
                        суммы в конце строк обязаны стоять ровным столбцом. */}
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center">
                      {hasChildren && (
                        <button
                          type="button"
                          aria-label={t("common.expand")}
                          onClick={() => setBreakdownItem(item)}
                          className="rounded-md p-0.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                        >
                          <SquareDivide size={15} />
                        </button>
                      )}
                    </span>
                    <span
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                      style={{ backgroundColor: `${item.color}26` }}
                    >
                      <Icon size={14} style={{ color: item.color }} />
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-text-primary">
                      {translateCategoryName(item.name)}
                    </span>
                    <span className="shrink-0 text-sm font-medium tabular-nums text-text-primary">
                      {formatCurrency(item.amount)}
                    </span>
                    </div>
                    {/* Полоса во всю ширину строки, а не между названием и
                        суммой: в узкой карточке на телефоне ей там осталось
                        бы пикселей тридцать, и сравнивать было бы нечего.

                        Дорожка под полосой нужна для нуля и для копеек:
                        без неё строка с пустой категорией выглядит как
                        строка, у которой полосу забыли нарисовать. */}
                    {view === "bars" && (
                      <span className="mt-1.5 block h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
                        <span
                          className="block h-full rounded-full"
                          style={{
                            width: largest > 0 ? `${(Number(item.amount) / largest) * 100}%` : 0,
                            // Совсем маленькая статья иначе исчезает целиком:
                            // полоски не видно, а деньги были.
                            minWidth: Number(item.amount) > 0 ? "4px" : undefined,
                            backgroundColor: item.color,
                          }}
                        />
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </CardContent>

      {breakdownItem && (
        <CategoryBreakdownModal
          open
          onClose={() => setBreakdownItem(null)}
          categoryId={breakdownItem.category_id ?? OTHER_SLICE_ID}
          categoryName={breakdownItem.name}
          totalAmount={breakdownItem.amount}
          children={breakdownItem.children}
        />
      )}
    </Card>
  );
}
