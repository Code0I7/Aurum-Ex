import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, Search } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * Выбор из длинного списка с поиском.
 *
 * Нативный `<select>` браузера хорош ровно до трёх десятков пунктов. Дальше
 * он превращается в столбик без поиска, который на телефоне ещё и
 * открывается системным колесом, никак не связанным с оформлением
 * приложения. У человека с сорока категориями добавление операции из-за
 * этого затягивается: нужную строку приходится искать глазами.
 *
 * Поэтому свой список: поле поиска сверху, отступы по вложенности,
 * управление с клавиатуры. Поиск идёт по полному пути категории, а не
 * только по её имени, — «прод сыр» находит «Продукты · Молочное · Сыр», и
 * помнить точное написание листа не нужно.
 *
 * Список рисуется порталом в body и позиционируется по месту кнопки.
 * Внутри диалога иначе никак: у окна операции своя прокрутка, и обычный
 * `absolute` в ней обрезался бы (та же причина, что у Dialog.tsx).
 */

export interface ComboboxOption {
  /** Значение строкой — как хранится в состоянии формы. */
  value: string;
  /** Что видно в списке и в кнопке. */
  label: string;
  /** Дополнительный текст для поиска: полный путь, синонимы. Не показывается. */
  search?: string;
  /** Уровень вложенности: отступ в списке. */
  depth?: number;
  /** Значок слева — для категорий и вообще где он есть. */
  icon?: React.ReactNode;
  /** Приглушённая подпись справа: счётчик, единица, что угодно. */
  hint?: string;
  /** Заголовок раздела. Одинаковый у идущих подряд пунктов — рисуется один
   *  раз над ними. Разделяет расходы и доходы в фильтрах, где в одном
   *  списке лежат и те и другие. */
  group?: string;
}

interface ComboboxProps {
  id?: string;
  options: ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  /** Подпись, когда ничего не выбрано. */
  placeholder: string;
  /** Подпись пустого пункта. Не задана — пустой выбор недоступен. */
  emptyLabel?: string;
  disabled?: boolean;
  className?: string;
  /** С какого числа пунктов показывать поиск. Для коротких списков поле
   *  поиска — лишний шаг. */
  searchFrom?: number;
}

/** Нормализация для поиска: регистр и «ё» не должны мешать найти. */
function normalize(text: string): string {
  return text.toLowerCase().replace(/ё/g, "е");
}

/**
 * Совпадение по словам, а не по подстроке: «прод сыр» должно находить
 * «Продукты · Молочное · Сыр». Требовать точного порядка букв значило бы
 * заставлять набирать разделители и промежуточные уровни.
 */
function matches(haystack: string, query: string): boolean {
  const target = normalize(haystack);
  return normalize(query)
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => target.includes(word));
}

export function Combobox({
  id,
  options,
  value,
  onChange,
  placeholder,
  emptyLabel,
  disabled,
  className,
  searchFrom = 8,
}: ComboboxProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ left: number; top: number; width: number; drop: "down" | "up" } | null>(null);

  const items = useMemo(() => {
    const all = emptyLabel !== undefined ? [{ value: "", label: emptyLabel }, ...options] : options;
    if (!query.trim()) return all;
    return all.filter((option) => matches(`${option.label} ${option.search ?? ""}`, query));
  }, [options, emptyLabel, query]);

  const selected = options.find((option) => option.value === value);

  // Положение списка считается от кнопки в момент открытия и пересчитывается
  // при прокрутке: портал живёт в body и о своей кнопке сам не знает.
  useLayoutEffect(() => {
    if (!open) return;
    function place() {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom;
      // Вниз, пока внизу есть куда: список у нижнего края экрана иначе
      // раскрывался бы за его пределы и был бы недоступен.
      const drop = below < 240 && rect.top > below ? "up" : "down";
      setBox({ left: rect.left, top: drop === "down" ? rect.bottom + 4 : rect.top - 4, width: rect.width, drop });
    }
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open]);

  // Закрытие по щелчку мимо. Проверяется и кнопка тоже: без этого щелчок по
  // ней закрывал бы список этим обработчиком и тут же открывал своим.
  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  useEffect(() => {
    if (open) return;
    setQuery("");
    setActive(0);
  }, [open]);

  // Подсветка съезжает на первый подходящий пункт при каждом наборе: иначе
  // Enter отправлял бы то, что выбрано было до поиска.
  useEffect(() => setActive(0), [query]);

  function choose(option: ComboboxOption) {
    onChange(option.value);
    setOpen(false);
    triggerRef.current?.focus();
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!items.length) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) => (current + step + items.length) % items.length);
      return;
    }
    if (event.key === "Enter") {
      // Enter внутри формы операции отправил бы её целиком, а человек лишь
      // выбирал пункт списка.
      event.preventDefault();
      const option = items[active];
      if (option) choose(option);
    }
  }

  const withSearch = items.length > searchFrom || query.trim() !== "";

  return (
    <>
      <button
        id={id}
        type="button"
        ref={triggerRef}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (!open && (event.key === "ArrowDown" || event.key === "Enter")) {
            event.preventDefault();
            setOpen(true);
          }
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={cn(
          "flex h-9 w-full items-center gap-2 rounded-lg border border-border bg-surface-1 px-3 text-left text-sm text-text-primary outline-none focus:border-series-1 disabled:opacity-50",
          className
        )}
      >
        {selected?.icon}
        <span className={cn("min-w-0 flex-1 truncate", !selected && "text-text-muted")}>
          {selected ? selected.label : (value === "" && emptyLabel) || placeholder}
        </span>
        <ChevronDown size={14} className="shrink-0 text-text-muted" />
      </button>

      {open && box
        ? createPortal(
            <div
              ref={panelRef}
              style={{
                left: box.left,
                width: box.width,
                ...(box.drop === "down" ? { top: box.top } : { bottom: window.innerHeight - box.top }),
              }}
              className="fixed z-[60] overflow-hidden rounded-lg border border-border bg-surface-1 shadow-xl"
              onKeyDown={onKeyDown}
            >
              {withSearch ? (
                <div className="flex items-center gap-2 border-b border-border px-3">
                  <Search size={14} className="shrink-0 text-text-muted" />
                  <input
                    autoFocus
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder={t("common.search")}
                    className="h-9 w-full bg-transparent text-sm text-text-primary outline-none"
                  />
                </div>
              ) : null}

              <div className="max-h-64 overflow-y-auto py-1">
                {items.length === 0 ? (
                  <p className="px-3 py-4 text-center text-xs text-text-muted">{t("common.nothingFound")}</p>
                ) : (
                  items.map((option, index) => (
                    <div key={option.value || "__empty"}>
                      {option.group && option.group !== items[index - 1]?.group ? (
                        <p className="px-3 pb-0.5 pt-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">
                          {option.group}
                        </p>
                      ) : null}
                    <button
                      type="button"
                      // pointerdown, а не click: щелчок мимо закрывает список
                      // раньше, чем click успевает дойти до пункта.
                      onPointerDown={(event) => {
                        event.preventDefault();
                        choose(option);
                      }}
                      onMouseEnter={() => setActive(index)}
                      className={cn(
                        "flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm",
                        index === active ? "bg-surface-2 text-text-primary" : "text-text-secondary"
                      )}
                      // Отступ по вложенности: ветка в три уровня без него
                      // читается как три равноправные категории подряд. При
                      // поиске отступов нет — там показан полный путь, и
                      // лесенка от найденных обрывков только мешает.
                      style={{ paddingLeft: 12 + (query.trim() ? 0 : (option.depth ?? 0) * 14) }}
                    >
                      {option.icon}
                      <span className="min-w-0 flex-1 truncate">
                        {query.trim() ? option.search || option.label : option.label}
                      </span>
                      {option.hint ? <span className="shrink-0 text-xs text-text-muted">{option.hint}</span> : null}
                      {option.value === value ? <Check size={14} className="shrink-0 text-accent" /> : null}
                    </button>
                    </div>
                  ))
                )}
              </div>
            </div>,
            document.body
          )
        : null}
    </>
  );
}
