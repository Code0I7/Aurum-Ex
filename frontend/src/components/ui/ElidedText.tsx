import { useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface ElidedTextProps {
  /** Полный текст, звенья которого разделены `separator`. */
  text: string;
  /** Чем разделены звенья. По умолчанию — как в categoryPath. */
  separator?: string;
  className?: string;
}

/**
 * Текст из звеньев, который при нехватке места теряет середину, а не конец.
 *
 * Обычная обрезка съедает самое важное. Путь категории кончается тем, что
 * человек искал: «Еда · Сладкое · Шоколад» в узкой ячейке превращался в
 * «Еда · Слад…», то есть в строке не оставалось ровно того слова, ради
 * которого она и написана. Здесь последнее звено не обрезается никогда, а
 * при нехватке места середина сворачивается в многоточие:
 * «Еда · … · Шоколад».
 *
 * Сворачивается только когда не влезает, а не всегда: если места хватает,
 * виден весь путь целиком.
 *
 * Цвет у всего текста один, как и был до появления сворачивания. Приглушать
 * начало пути ради «последнее звено главное» не стоит: и так понятно, что
 * последнее — это сама категория, а два цвета в строке читаются как
 * подсветка неизвестно чего.
 *
 * Решение принимается по невидимой копии полного текста, а не по самому
 * тексту на экране. Измерять уже свёрнутое бессмысленно: оно, конечно,
 * влезает — и его тут же развернули бы обратно, а оно опять не влезло бы, и
 * так по кругу.
 *
 * Полный текст остаётся в подсказке при наведении: свёрнутая середина должна
 * быть доступна, а не потеряна.
 */
export function ElidedText({ text, separator = " · ", className }: ElidedTextProps) {
  const hostRef = useRef<HTMLSpanElement>(null);
  const probeRef = useRef<HTMLSpanElement>(null);
  const [collapsed, setCollapsed] = useState(false);

  const segments = text.split(separator);
  const leaf = segments[segments.length - 1];
  const parents = segments.slice(0, -1);
  // Сворачивать нечего, пока звеньев меньше трёх: середины у такого текста
  // нет. Заодно это избавляет от измерений там, где они не нужны, — в списке
  // категорий длинные пути единичны, а строк бывает сотня.
  const collapsible = segments.length > 2;

  useLayoutEffect(() => {
    if (!collapsible) {
      setCollapsed(false);
      return;
    }
    const host = hostRef.current;
    const probe = probeRef.current;
    if (!host || !probe) return;
    // offsetWidth и clientWidth — оба в тех же единицах, в которых задана
    // разметка, поэтому увеличенный интерфейс сравнение не ломает.
    const measure = () => setCollapsed(probe.offsetWidth > host.clientWidth + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(host);
    return () => observer.disconnect();
  }, [collapsible, text, separator]);

  const head = collapsed ? `${segments[0]}${separator}…` : parents.join(separator);
  // Разделитель перед последним звеном — с неразрывными пробелами. Обычные
  // на конце строки браузер убирает, и «Еда · » с последним звеном рядом
  // склеивались в «Еда ·Шоколад»: начало и конец здесь лежат в разных
  // элементах, то есть в разных строках с точки зрения переноса.
  const gap = separator.replace(/ /g, " ");

  return (
    <span
      ref={hostRef}
      className={cn("relative flex min-w-0 items-baseline whitespace-nowrap", className)}
      title={text}
    >
      {collapsible && (
        <span ref={probeRef} aria-hidden className="pointer-events-none invisible absolute left-0 top-0">
          {text}
        </span>
      )}
      {parents.length > 0 && (
        // Начало обрезается, если и свёрнутое не влезло: у двухзвенного
        // пути сворачивать нечего, а конец и там должен остаться целым.
        <span className="min-w-0 truncate">
          {head}
          {gap}
        </span>
      )}
      <span className="shrink-0">{leaf}</span>
    </span>
  );
}
