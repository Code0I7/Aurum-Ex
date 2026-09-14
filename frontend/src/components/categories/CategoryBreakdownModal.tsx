import { useEffect, useState } from "react";
import { ChevronLeft, SquareDivide } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";

interface CategoryBreakdownChild {
  category_id: number;
  name: string;
  color: string;
  icon: string | null;
  amount: string;
  /** Разбивка самой строки. Бывает только у строк доли «Прочее»: там
   *  строка — целая категория верхнего уровня, и у неё могут быть свои
   *  подкатегории, как у «Еды» в основном списке. */
  children?: CategoryBreakdownChild[];
}

interface CategoryBreakdownModalProps {
  open: boolean;
  onClose: () => void;
  categoryId: number;
  categoryName: string;
  totalAmount: string;
  children: CategoryBreakdownChild[];
}

/** Один открытый уровень разбивки. */
interface BreakdownLevel {
  categoryId: number;
  categoryName: string;
  totalAmount: string;
  children: CategoryBreakdownChild[];
}

/** Shows how a parent category's total splits across its subcategories — a
 * modal rather than an inline expansion, since a category with many
 * subcategories (or many split-across purchases) would otherwise push the
 * Dashboard's donut/list layout out of alignment as rows grow taller. Shared
 * between the Dashboard breakdown and the Reports category ranking, which
 * expose the same shape (see services/category_rollup.py's
 * CategoryRollupChildItem).
 *
 * Строка со своей разбивкой открывается в этом же окне, а не вторым окном
 * поверх: окно в окне на телефоне закрывало бы весь экран дважды, и
 * вернуться к списку «Прочего» можно было бы, только закрыв оба. Стрелка у
 * заголовка возвращает на уровень выше. */
export function CategoryBreakdownModal({
  open,
  onClose,
  categoryId,
  categoryName,
  totalAmount,
  children,
}: CategoryBreakdownModalProps) {
  const { t } = useTranslation();
  // Уровни, открытые поверх исходного. Исходный берётся из свойств, а не
  // копируется сюда: иначе обновлённые данные обзора не доходили бы до уже
  // открытого окна.
  const [nested, setNested] = useState<BreakdownLevel[]>([]);

  // Закрытое окно открывается заново с начала, а не с того уровня, на
  // котором его закрыли.
  useEffect(() => {
    if (!open) setNested([]);
  }, [open]);

  const level: BreakdownLevel = nested[nested.length - 1] ?? {
    categoryId,
    categoryName,
    totalAmount,
    children,
  };
  const total = Number(level.totalAmount);
  // Место под кнопку разбивки — только если она есть хоть у одной строки:
  // в обычной разбивке подкатегорий пустой отступ слева был бы ни к чему, а
  // внутри уровня суммы обязаны стоять ровным столбцом.
  const anyNested = level.children.some((child) => (child.children?.length ?? 0) > 0);

  const title =
    nested.length > 0 ? (
      <span className="flex min-w-0 items-center gap-1">
        <button
          type="button"
          aria-label={t("common.back")}
          onClick={() => setNested((prev) => prev.slice(0, -1))}
          className="-ml-1 rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary"
        >
          <ChevronLeft size={18} />
        </button>
        <span className="truncate">{translateCategoryName(level.categoryName)}</span>
      </span>
    ) : (
      translateCategoryName(level.categoryName)
    );

  return (
    <Dialog open={open} onClose={onClose} title={title}>
      <div className="mb-3 flex items-center justify-between border-b border-gridline pb-3 text-sm">
        <span className="text-text-muted">{t("reports.categoryBreakdownTotalLabel")}</span>
        <span className="font-semibold tabular-nums text-text-primary">{formatCurrency(level.totalAmount)}</span>
      </div>
      <ul className="divide-y divide-gridline">
        {level.children.map((child) => {
          const Icon = getCategoryIcon(child.icon);
          const percent = total ? (Number(child.amount) / total) * 100 : 0;
          const label =
            child.category_id === level.categoryId ? t("reports.directSpendLabel") : translateCategoryName(child.name);
          const grandchildren = child.children ?? [];
          const openNested = () =>
            setNested((prev) => [
              ...prev,
              {
                categoryId: child.category_id,
                categoryName: child.name,
                totalAmount: child.amount,
                children: grandchildren,
              },
            ]);
          return (
            <li key={child.category_id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
              {anyNested && (
                <span className="-mr-1 flex h-6 w-6 shrink-0 items-center justify-center">
                  {grandchildren.length > 0 && (
                    <button
                      type="button"
                      aria-label={t("common.expand")}
                      onClick={openNested}
                      className="rounded-md p-0.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                    >
                      <SquareDivide size={15} />
                    </button>
                  )}
                </span>
              )}
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                style={{ backgroundColor: `${child.color}26` }}
              >
                <Icon size={15} style={{ color: child.color }} />
              </span>
              {/* Название тоже открывает разбивку: на телефоне одна кнопка
                  со значком — слишком мелкая цель для пальца. */}
              {grandchildren.length > 0 ? (
                <button
                  type="button"
                  onClick={openNested}
                  className="min-w-0 flex-1 truncate text-left text-sm text-text-primary hover:underline"
                >
                  {label}
                </button>
              ) : (
                <span className="min-w-0 flex-1 truncate text-sm text-text-primary">{label}</span>
              )}
              <span className="w-9 shrink-0 text-right text-xs text-text-muted tabular-nums">
                {percent.toFixed(0)}%
              </span>
              <span className="shrink-0 text-sm font-medium tabular-nums text-text-primary">
                {formatCurrency(child.amount)}
              </span>
            </li>
          );
        })}
      </ul>
    </Dialog>
  );
}
