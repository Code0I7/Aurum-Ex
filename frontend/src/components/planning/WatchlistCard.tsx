import { useMemo, useState } from "react";
import { Eye, Search, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { useCategories, useUpdateCategory } from "@/hooks/useCategories";
import { useWatchlist } from "@/hooks/usePlans";
import { getLanguage, useTranslation } from "@/lib/i18n";
import {
  buildHierarchicalCategories,
  categoryOptionPrefix,
  translateCategoryName,
} from "@/lib/categoryLabels";
import { formatCurrency, getMonthLabels } from "@/lib/format";
import type { WatchRow } from "@/types";

/**
 * Список наблюдения — то, чем в исходной таблице был лист «Отследить».
 *
 * Там выбирали несколько подкатегорий и выписывали их по месяцам вручную,
 * с переключателями «Вкл/Выкл». Смысл не в том, чтобы видеть все категории
 * сразу — для этого есть таблица года выше, — а в обратном: держать перед
 * глазами те три-четыре, за которыми следишь прямо сейчас.
 *
 * Отдельная карточка, а не режим таблицы года, потому что правила у строк
 * другие: суммы берутся по всей ветке, план не нужен, и рядом стоит
 * прошлый год — вопрос ведь не «сколько», а «больше или меньше, чем было».
 */
export function WatchlistCard({ year }: { year: number }) {
  const { t, language } = useTranslation();
  const { data: watchlist, isLoading } = useWatchlist(year);
  const [pickerOpen, setPickerOpen] = useState(false);
  const months = getMonthLabels(getLanguage());

  const rows = watchlist?.rows ?? [];

  return (
    <Card>
      <CardHeader className="items-start">
        <div className="flex items-center gap-2">
          <CardTitle>{t("watchlist.title")}</CardTitle>
          <HelpBadge hintKey="watchlist.hint" />
        </div>
        <Button variant="secondary" onClick={() => setPickerOpen(true)}>
          <Eye size={16} />
          {t("watchlist.choose")}
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="py-8 text-center text-sm text-text-muted">{t("common.loading")}</p>
        ) : rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-muted">{t("watchlist.empty")}</p>
        ) : (
          // Двенадцать месяцев не помещаются на телефон ни при каком
          // раскладе: таблица прокручивается вбок, название прибито слева.
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-separate border-spacing-0 text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-wide text-text-muted">
                  <th className="sticky left-0 z-10 bg-surface-1 py-2 pr-3 text-left font-medium">
                    {t("planning.category")}
                  </th>
                  {months.map((label) => (
                    <th key={label} className="px-2 py-2 text-right font-medium">
                      {label.slice(0, 3)}
                    </th>
                  ))}
                  <th className="py-2 pl-3 text-right font-medium">{t("planning.year")}</th>
                  <th className="py-2 pl-3 text-right font-medium">{year - 1}</th>
                  <th className="py-2 pl-3 text-right font-medium">{t("watchlist.change")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <WatchTableRow key={row.category_id} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      <WatchlistPicker open={pickerOpen} onClose={() => setPickerOpen(false)} language={language} />
    </Card>
  );
}

function WatchTableRow({ row }: { row: WatchRow }) {
  const total = Number(row.total);
  const previous = Number(row.previous_total);
  // Процент считается только когда есть от чего считать: рост с нуля не
  // «бесконечный процент», а просто «раньше этого не было».
  const change = previous > 0 ? ((total - previous) / previous) * 100 : null;
  // Для расхода рост — плохо, для дохода — хорошо.
  const good = row.kind === "income" ? change !== null && change > 0 : change !== null && change < 0;

  return (
    <tr className="border-b border-border/40">
      {/* Путь приходит с сервера именами из базы, а стандартные категории
          хранятся там по-английски: без перевода в русском интерфейсе
          строка читалась «Dining Out», хотя во всех остальных таблицах —
          «Кафе и рестораны». Разделитель тот же, что у сервера. */}
      <th className="sticky left-0 z-10 truncate bg-surface-1 py-2 pr-3 text-left font-normal">
        {row.path.split(" · ").map(translateCategoryName).join(" · ")}
      </th>
      {row.months.map((amount, index) => (
        <td key={index} className="px-2 py-2 text-right tabular-nums text-text-secondary">
          {Number(amount) === 0 ? (
            <span className="text-text-muted">—</span>
          ) : (
            formatCurrency(amount)
          )}
        </td>
      ))}
      <td className="py-2 pl-3 text-right font-semibold tabular-nums">{formatCurrency(total)}</td>
      <td className="py-2 pl-3 text-right tabular-nums text-text-muted">
        {previous === 0 ? "—" : formatCurrency(previous)}
      </td>
      <td
        className={`py-2 pl-3 text-right tabular-nums ${
          change === null ? "text-text-muted" : good ? "text-success" : "text-danger"
        }`}
      >
        {change === null ? "—" : `${change > 0 ? "+" : ""}${change.toFixed(0)}%`}
      </td>
    </tr>
  );
}

/**
 * Кто в списке. Переключатели, а не отдельный экран управления: список
 * наблюдения меняют часто и по одному — сегодня смотрят за такси, через
 * месяц за подписками.
 */
function WatchlistPicker({
  open,
  onClose,
  language,
}: {
  open: boolean;
  onClose: () => void;
  language: string;
}) {
  const { t } = useTranslation();
  const { data: categories } = useCategories();
  const updateCategory = useUpdateCategory();
  const [query, setQuery] = useState("");

  const ordered = useMemo(
    () => buildHierarchicalCategories(categories ?? [], language),
    [categories, language]
  );

  const search = query.trim().toLowerCase();
  // При поиске дерево разворачивается в плоский список: отступы у
  // отфильтрованных строк указывали бы на родителей, которых на экране нет.
  const visible = search
    ? ordered.filter((category) => translateCategoryName(category.name).toLowerCase().includes(search))
    : ordered;

  return (
    <Dialog open={open} onClose={onClose} title={t("watchlist.choose")}>
      <div className="relative mb-3">
        <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("watchlist.searchPlaceholder")}
          className="pl-9 pr-9"
        />
        {query && (
          <button
            type="button"
            aria-label={t("common.clear")}
            onClick={() => setQuery("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-text-muted hover:bg-surface-2"
          >
            <X size={15} />
          </button>
        )}
      </div>

      {/* Половина экрана — в единицах разметки: `50vh` внутри увеличенного
          корня умножается на масштаб второй раз, и при 150% список занимал
          три четверти экрана, а при 300% не помещался в него вовсе. */}
      <div className="max-h-[calc(var(--app-vh)*0.5)] space-y-0.5 overflow-y-auto">
        {visible.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-muted">{t("watchlist.nothingFound")}</p>
        ) : (
          visible.map((category) => (
            <label
              key={category.id}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-2"
            >
              <input
                type="checkbox"
                checked={category.is_watched}
                onChange={(event) =>
                  updateCategory.mutate({ id: category.id, input: { is_watched: event.target.checked } })
                }
                className="h-3.5 w-3.5 shrink-0 accent-text-primary"
              />
              <span className="min-w-0 flex-1 truncate">
                {search ? "" : categoryOptionPrefix(category.depth)}
                {translateCategoryName(category.name)}
              </span>
              <span className="shrink-0 text-xs text-text-muted">
                {category.kind === "income" ? t("planning.incomeTotal") : t("planning.expenseTotal")}
              </span>
            </label>
          ))
        )}
      </div>

      <div className="mt-4 flex justify-end">
        <Button onClick={onClose}>{t("common.done")}</Button>
      </div>
    </Dialog>
  );
}
