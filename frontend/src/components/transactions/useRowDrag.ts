import { useCallback, useRef, useState } from "react";
import type { Transaction } from "@/types";

/**
 * Перетаскивание строки таблицы за ручку — как в списке воспроизведения:
 * схватил за полоски слева, потащил, увидел, куда встанет, отпустил.
 *
 * Сделано на указательных событиях, а не на HTML5 drag-and-drop, по двум
 * причинам. Первая: HTML5 drag не работает на сенсорных экранах вовсе, а
 * половина ввода делается с телефона. Вторая: у него нельзя нарисовать
 * собственный указатель вставки — браузер сам решает, как показать
 * перетаскивание, и выглядит это по-разному везде.
 *
 * `touch-action: none` на ручке (см. TransactionsGrid) обязателен: без него
 * палец, начавший движение по вертикали, прокручивает страницу вместо
 * перетаскивания строки.
 *
 * Переставлять можно только внутри одного дня и одного счёта: день меняют
 * редактированием даты, а порядок операций разных счетов друг на друга не
 * влияет — у каждого своя нумерация.
 */

export interface DragState {
  /** Идентификатор перетаскиваемой операции. */
  id: number;
  /** Визуальная позиция, на которую строка встанет, если отпустить сейчас. */
  targetIndex: number;
}

interface RowMeta {
  transaction: Transaction;
  /** Позиция строки среди операций того же дня и счёта, сверху вниз. */
  indexInDay: number;
}

export function useRowDrag(
  onReorder: (transaction: Transaction, visualIndex: number, countInDay: number) => void
) {
  const [drag, setDrag] = useState<DragState | null>(null);
  // Живые данные перетаскивания держим в ref, а не в состоянии: обработчик
  // движения срабатывает десятки раз в секунду, и перерисовывать таблицу на
  // каждое движение мыши незачем — перерисовка нужна только когда меняется
  // строка, над которой мы находимся.
  const session = useRef<{ row: RowMeta; siblings: RowMeta[]; targetIndex: number } | null>(null);

  const start = useCallback((event: React.PointerEvent, row: RowMeta, siblings: RowMeta[]) => {
    // Тащим только основной кнопкой или пальцем: правый клик и средняя
    // кнопка не должны начинать перетаскивание.
    if (event.button !== 0) return;
    event.preventDefault();
    (event.target as HTMLElement).setPointerCapture?.(event.pointerId);
    session.current = { row, siblings, targetIndex: row.indexInDay };
    setDrag({ id: row.transaction.id, targetIndex: row.indexInDay });
  }, []);

  const move = useCallback((event: React.PointerEvent) => {
    const current = session.current;
    if (!current) return;

    // Строку под курсором ищем через элемент в точке, а не по координатам
    // строк: так работает и при прокрутке списка во время перетаскивания.
    const element = document.elementFromPoint(event.clientX, event.clientY);
    const rowElement = element?.closest<HTMLElement>("[data-row-id]");
    if (!rowElement) return;

    const overId = Number(rowElement.dataset.rowId);
    const over = current.siblings.find((item) => item.transaction.id === overId);
    // Строка другого дня или счёта — не цель: там своя нумерация.
    if (!over) return;

    if (over.indexInDay !== current.targetIndex) {
      current.targetIndex = over.indexInDay;
      setDrag({ id: current.row.transaction.id, targetIndex: over.indexInDay });
    }
  }, []);

  const end = useCallback(() => {
    const current = session.current;
    session.current = null;
    setDrag(null);
    if (!current) return;
    if (current.targetIndex === current.row.indexInDay) return;
    onReorder(current.row.transaction, current.targetIndex, current.siblings.length);
  }, [onReorder]);

  return { drag, start, move, end };
}
