import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useBubbleShift } from "@/hooks/useBubbleShift";
import { currentZoom, layoutViewport } from "@/lib/scale";
import { cn } from "@/lib/utils";

interface HintBubbleProps {
  /** Короткая строка в пузыре. Пусто — пузыря нет вовсе. */
  note: string | null | undefined;
  /** То, рядом с чем он появляется. */
  children: ReactNode;
  className?: string;
}

/** Зазор между числом и пузырём, в единицах разметки. */
const GAP = 6;

/**
 * Пузырь с точным числом рядом с округлённым.
 *
 * Появился вместо системной подсказки (`title`), и причина простая: та
 * рисуется у курсора и курсором же перекрывается — именно то число, за
 * которым к ней и потянулись, оказывается под стрелкой.
 *
 * Встаёт **слева** от содержимого, и это не произвол. Сверху нельзя: и в
 * списке крупнейших трат, и в строке таблицы прямо над ценой в днях стоит
 * сама сумма, и пузырь закрывал бы её — то есть ровно то число, с которым
 * его и сравнивают. Снизу тоже плохо: стрелка курсора растёт вправо и вниз
 * от своей точки. Слева от числа пусто, а курсор остаётся правее.
 *
 * Рисуется порталом в body и позиционируется по месту числа — по той же
 * причине, что и список в Combobox: у таблицы операций своя горизонтальная
 * прокрутка, а она обрезает всё, что выходит за ячейку. Обычный `absolute`
 * там показывал от пузыря половину, обрезанную по краю ячейки.
 *
 * Открывается и по наведению, и по нажатию. Это не дублирование ради
 * дублирования, как у значка «!», где выбран только клик: там подсказка —
 * абзац текста, который читают один раз, а здесь число, на которое смотрят
 * мимоходом. Наведение для мыши быстрее клика, а на телефоне наведения нет
 * вовсе, и без нажатия число стало бы недоступным.
 */
export function HintBubble({ note, children, className }: HintBubbleProps) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLSpanElement>(null);
  const bubble = useRef<HTMLSpanElement>(null);
  // Место пузыря в единицах разметки: правый край прижат к левому краю
  // числа, середина по высоте — к его середине.
  const [box, setBox] = useState<{
    right: number;
    top: number;
    fontSize: string;
    lineHeight: string;
  } | null>(null);
  // Сдвиг, если слева не хватило экрана. Считается после того, как пузырь
  // отрисован и его можно измерить, — отсюда зависимость от box.
  const shift = useBubbleShift(open && box !== null, bubble);

  useLayoutEffect(() => {
    if (!open) {
      setBox(null);
      return;
    }
    const node = anchor.current;
    if (!node) return;
    // Всё, что пришло с экрана, делится на множитель увеличения: ниже эти
    // числа станут `top` и `right` элемента с `position: fixed`, а он
    // считает свои координаты в неувеличенных единицах (см. lib/scale.ts).
    const zoom = currentZoom();
    const rect = node.getBoundingClientRect();
    const view = layoutViewport();
    // Шрифт берётся у числа, рядом с которым пузырь встаёт, и это не
    // косметика. Совпадения коробок мало: буквы сидят в строке по своим
    // метрикам, и при разном межстрочном интервале два отцентрованных по
    // коробкам текста расходятся по вертикали. У пузыря стоял leading-none
    // против обычного у строки — ровно отсюда и брались те две с половиной
    // точки, которые видно глазом и не видно замеру коробок.
    //
    // Портал лежит в body, и унаследовать шрифт ему неоткуда: он
    // переносится руками.
    const style = getComputedStyle(node);
    setBox({
      right: view.width - rect.left / zoom + GAP,
      top: (rect.top + rect.height / 2) / zoom,
      fontSize: style.fontSize,
      lineHeight: style.lineHeight,
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function close() {
      setOpen(false);
    }
    function onPointerDown(event: PointerEvent) {
      if (!anchor.current?.contains(event.target as Node)) close();
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    // Пузырь прибит к экрану, а число уезжает вместе с прокруткой: вместо
    // того чтобы гнаться за ним, проще закрыться. Слушается в фазе
    // перехвата — иначе прокрутка таблицы, у которой своя полоса, до окна
    // не доходит и остаётся незамеченной.
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  if (!note) return <>{children}</>;

  return (
    <>
      <span
        ref={anchor}
        // Не кнопка: это число в строке таблицы, и объявлять его кнопкой
        // значило бы обещать действие, которого нет.
        role="note"
        tabIndex={0}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={() => setOpen((value) => !value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        // items-center: иначе коробка обёртки выше своего текста на
        // межстрочный интервал, и середина у них перестаёт совпадать.
        className={cn("inline-flex items-center cursor-help touch-manipulation", className)}
      >
        {children}
      </span>

      {open && box
        ? createPortal(
            <span
              ref={bubble}
              style={{
                right: box.right,
                top: box.top,
                transform: `translate(${shift}px, -50%)`,
                fontSize: box.fontSize,
                lineHeight: box.lineHeight,
              }}
              role="tooltip"
              className={cn(
                "pointer-events-none fixed z-[60] whitespace-nowrap",
                "rounded-md border border-border bg-surface-1 px-2 py-1 font-normal",
                "normal-case tracking-normal text-text-secondary shadow-lg"
              )}
            >
              {note}
            </span>,
            document.body
          )
        : null}
    </>
  );
}
