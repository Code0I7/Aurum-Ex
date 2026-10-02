import { useLayoutEffect, useState, type RefObject } from "react";
import { horizontalShift } from "@/lib/bubble";
import { currentZoom } from "@/lib/scale";

/**
 * Сдвиг открытого пузыря, чтобы он не уехал за край экрана.
 *
 * Тонкая обёртка над измерением: вся арифметика живёт в lib/bubble.ts и
 * проверена отдельно, здесь только замер живого элемента и перевод единиц.
 *
 * Перевод важен: getBoundingClientRect и innerWidth отдают пиксели экрана —
 * уже увеличенные, — а сдвиг ставится в пикселях разметки. При увеличенном
 * интерфейсе это разные единицы, и подстановка одного вместо другого
 * промахивается ровно во столько раз, во сколько увеличен интерфейс (см.
 * lib/scale.ts).
 */
export function useBubbleShift(open: boolean, bubble: RefObject<HTMLElement | null>): number {
  const [shift, setShift] = useState(0);

  useLayoutEffect(() => {
    if (!open) {
      setShift(0);
      return;
    }
    const node = bubble.current;
    if (!node) return;
    const zoom = currentZoom();
    const rect = node.getBoundingClientRect();
    setShift(horizontalShift(rect, window.innerWidth, 8 * zoom) / zoom);
  }, [open, bubble]);

  return shift;
}
