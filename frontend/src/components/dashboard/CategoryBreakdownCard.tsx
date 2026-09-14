import { useState } from "react";
import { SquareDivide } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { CategoryBreakdownModal } from "@/components/categories/CategoryBreakdownModal";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { CategoryBreakdownItem } from "@/types";

interface CategoryBreakdownCardProps {
  title: string;
  /** Что сказать, когда за период нет ни одной операции этого вида. */
  emptyLabel: string;
  items: CategoryBreakdownItem[];
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
export function CategoryBreakdownCard({ title, emptyLabel, items, className }: CategoryBreakdownCardProps) {
  const { t } = useTranslation();
  // Разбивка — в окне, а не раскрытием в строке: категория с десятком
  // подкатегорий иначе растянула бы карточку и сломала бы ровный край с
  // соседними.
  const [breakdownItem, setBreakdownItem] = useState<CategoryBreakdownItem | null>(null);
  const hasData = items.length > 0;
  // Recharts нужна числовая величина, а суммы с сервера приходят строками.
  const chartData = items.map((item) => ({ ...item, amount: Number(item.amount) }));

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {!hasData ? (
          <p className="py-10 text-center text-sm text-text-muted">{emptyLabel}</p>
        ) : (
          <div className="chart-palette flex flex-col items-center gap-4">
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

            <ul className="w-full min-w-0 divide-y divide-gridline">
              {items.map((item) => {
                const Icon = getCategoryIcon(item.icon);
                const hasChildren = item.children.length > 0;
                return (
                  <li
                    key={item.category_id ?? "other"}
                    className="flex items-center gap-2 py-2 first:pt-0 last:pb-0"
                  >
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
