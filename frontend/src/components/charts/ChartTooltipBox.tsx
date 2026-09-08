import type { PropsWithChildren } from "react";
import { cn } from "@/lib/utils";

/**
 * Рамка всплывающей подсказки графика — одна на все графики.
 *
 * Раньше та же строка классов была выписана в восьми местах, и подсказки
 * незаметно разъезжались: где-то мелкий шрифт, где-то обычный. Здесь же
 * висит и появление: класс `chart-tooltip` (index.css) даёт короткое
 * проявление на месте.
 *
 * Само появление пришлось чинить отдельно. Recharts по умолчанию
 * анимирует положение подсказки, и первая на странице приезжала из левого
 * верхнего угла через весь график — глаз следил за движением вместо того,
 * чтобы читать число. Отключается это не здесь, а свойством
 * `isAnimationActive={false}` у самого `<Tooltip>`: рамка своим положением
 * не распоряжается.
 */
export function ChartTooltipBox({ className, children }: PropsWithChildren<{ className?: string }>) {
  return (
    <div
      className={cn(
        "chart-tooltip rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm shadow-md",
        className
      )}
    >
      {children}
    </div>
  );
}
