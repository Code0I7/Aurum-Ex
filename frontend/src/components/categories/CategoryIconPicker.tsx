import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { CATEGORY_ICON_OPTIONS, ICON_GROUPS, type IconGroupKey, type IconOption } from "@/lib/icons";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface CategoryIconPickerProps {
  value: string;
  onChange: (icon: string) => void;
}

/**
 * Выбор значка категории.
 *
 * Раньше это была сетка из тридцати семи глифов подряд, без единого
 * заголовка и без поиска: найти нужный можно было только перебором глазами.
 * Теперь значков под сотню, и перебор перестал работать окончательно —
 * отсюда разделы по смыслу и поле поиска.
 *
 * Поиск идёт по русским и английским словам, а не по имени глифа: «вода»
 * должно находить каплю, не заставляя догадываться, что она называется
 * `droplet`. При поиске заголовки разделов не показываются — среди трёх
 * найденных значков они только шум.
 */
export function CategoryIconPicker({ value, onChange }: CategoryIconPickerProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");

  const search = query.trim().toLowerCase().replace(/ё/g, "е");
  const found = useMemo(
    () =>
      search
        ? CATEGORY_ICON_OPTIONS.filter((option) =>
            `${option.key} ${option.keywords}`.toLowerCase().replace(/ё/g, "е").includes(search)
          )
        : CATEGORY_ICON_OPTIONS,
    [search]
  );

  // Раскладка по разделам считается один раз на набор, а не в разметке:
  // иначе список фильтровался бы заново для каждого из одиннадцати
  // заголовков.
  const byGroup = useMemo(() => {
    const map = new Map<IconGroupKey, IconOption[]>();
    for (const option of found) {
      const bucket = map.get(option.group);
      if (bucket) bucket.push(option);
      else map.set(option.group, [option]);
    }
    return map;
  }, [found]);

  function grid(options: IconOption[]) {
    return (
      <div className="grid grid-cols-6 gap-1.5 sm:grid-cols-10">
        {options.map((option) => {
          const Icon = option.component;
          const selected = option.key === value;
          return (
            <button
              key={option.key}
              type="button"
              aria-label={option.key}
              aria-pressed={selected}
              title={option.key}
              onClick={() => onChange(option.key)}
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg border transition-colors",
                selected
                  ? "border-series-1 bg-series-1/10 text-series-1"
                  : "border-border text-text-secondary hover:bg-surface-2"
              )}
            >
              <Icon size={16} />
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("icons.searchPlaceholder")}
          className="pl-9 pr-9"
        />
        {query && (
          <button
            type="button"
            aria-label={t("common.clear")}
            onClick={() => setQuery("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-text-muted hover:bg-surface-2"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {/* Своя прокрутка: под сотню значков в одиннадцати разделах иначе
          растягивают форму категории на два экрана, и кнопка сохранения
          уезжает за край. */}
      <div className="max-h-64 space-y-3 overflow-y-auto pr-1">
        {found.length === 0 ? (
          <p className="py-6 text-center text-xs text-text-muted">{t("common.nothingFound")}</p>
        ) : search ? (
          grid(found)
        ) : (
          ICON_GROUPS.map((group) => {
            const options = byGroup.get(group.key);
            if (!options?.length) return null;
            return (
              <div key={group.key}>
                <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-text-muted">
                  {t(group.labelKey)}
                </p>
                {grid(options)}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
