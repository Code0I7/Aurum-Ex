import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { CategoryRankingChildItem, CategoryRankingItem } from "@/types";

interface CategoryRankingCardProps {
  items: CategoryRankingItem[];
  isLoading: boolean;
  selectedCategoryId: number | null;
  onSelectCategory: (categoryId: number) => void;
}

/** Ranks every expense category by total spent over the currently selected
 * period — unlike the Dashboard breakdown (locked to one month) or the
 * detail chart below (locked to one category), this is "which category
 * costs the most" across the whole range at once. Clicking a row drills
 * into that category in the detail chart/transaction list below. */
// A child's category_id equals its parent's own — the enclosing
// CategoryRankingItem's — when that slice of spend was filed directly on
// the parent with no more specific subcategory chosen (see
// services/category_rollup.py's CategoryRollupChildItem).
function childLabel(child: CategoryRankingChildItem, parentId: number, t: (key: TranslationKey) => string) {
  return child.category_id === parentId ? t("reports.directSpendLabel") : translateCategoryName(child.name);
}

export function CategoryRankingCard({ items, isLoading, selectedCategoryId, onSelectCategory }: CategoryRankingCardProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function toggle(categoryId: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
      return next;
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("reports.categoryRankingTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
        ) : items.length === 0 ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("reports.noRankingData")}</p>
        ) : (
          <ul className="divide-y divide-gridline">
            {items.map((item, index) => {
              const Icon = getCategoryIcon(item.icon);
              const isSelected = item.category_id === selectedCategoryId;
              const hasChildren = item.children.length > 0;
              const isExpanded = expanded.has(item.category_id);
              return (
                <li key={item.category_id}>
                  <div
                    className={`flex items-center gap-1 rounded-lg transition-colors hover:bg-surface-2 ${
                      isSelected ? "bg-surface-2" : ""
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => onSelectCategory(item.category_id)}
                      className="flex flex-1 items-center gap-3 py-2.5 text-left"
                    >
                      <span className="w-4 shrink-0 text-right text-xs tabular-nums text-text-muted">{index + 1}</span>
                      <span
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                        style={{ backgroundColor: `${item.color}26` }}
                      >
                        <Icon size={15} style={{ color: item.color }} />
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm text-text-primary">
                        {translateCategoryName(item.name)}
                      </span>
                      <span className="hidden w-24 shrink-0 items-center gap-2 sm:flex">
                        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                          <span
                            className="block h-full rounded-full"
                            style={{ width: `${item.percent}%`, backgroundColor: item.color }}
                          />
                        </span>
                        <span className="w-9 shrink-0 text-right text-xs text-text-muted tabular-nums">
                          {item.percent.toFixed(0)}%
                        </span>
                      </span>
                      <span className="shrink-0 text-sm font-medium tabular-nums text-text-primary">
                        {formatCurrency(item.amount)}
                      </span>
                    </button>
                    {hasChildren && (
                      <button
                        type="button"
                        aria-label={isExpanded ? t("common.collapse") : t("common.expand")}
                        onClick={() => toggle(item.category_id)}
                        className="mr-1 shrink-0 rounded-md p-1.5 text-text-muted hover:text-text-primary"
                      >
                        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </button>
                    )}
                  </div>

                  {hasChildren && isExpanded && (
                    <ul className="ml-11 mb-2 mt-1 space-y-1 border-l border-gridline pl-3">
                      {item.children.map((child) => (
                        <li key={child.category_id} className="flex items-center gap-2 text-xs">
                          <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: child.color }} />
                          <span className="min-w-0 flex-1 truncate text-text-secondary">
                            {childLabel(child, item.category_id, t)}
                          </span>
                          <span className="shrink-0 tabular-nums text-text-secondary">
                            {formatCurrency(child.amount)}
                          </span>
                        </li>
                      ))}
                    </ul>
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
