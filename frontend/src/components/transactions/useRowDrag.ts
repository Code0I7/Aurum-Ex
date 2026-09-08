import { useCallback, useRef, useState } from "react";
import type { Transaction } from "@/types";

/**
 * Перетаскивание строки таблицы за само её тело.
 *
 * Сделано на указательных событиях, а не на HTML5 drag-and-drop, по двум
 * причинам. Первая: HTML5 drag не работает на сенсорных экранах вовсе, а
 * половина ввода делается с телефона. Вторая: у него нельзя нарисовать
 * собственный указатель вставки — браузер сам решает, как показать
 * перетаскивание, и выглядит это по-разному везде.
 *
 * Мышью строку тянут за любое место, но не сразу: перетаскивание
 * начинается, только когда указатель ушёл дальше нескольких точек. Без
 * этого порога щелчок по строке — а он открывает правку — каждый раз
 * оказывался бы микроперетаскиванием, и порядок операций менялся бы от
 * дрожания руки.
 *
 * Пальцем так нельзя, и это ограничение не обходится. Браузер решает,
 * прокрутка это или жест, в момент касания: чтобы отдать движение нам, у
 * строки должен стоять `touch-action: none` **заранее** — то есть список
 * перестал бы прокручиваться вовсе. Поэтому на узких экранах остаётся
 * ручка: это свойство стоит только на ней, а всё остальное прокручивается
 * как обычно.
 *
 * Переставлять можно только внутри одного дня и одного счёта: день меняют
 * редактированием даты, а порядок операций разных счетов друг на друга не
 * влияет — у каждого своя нумерация.
 */

/** Насколько указатель должен уйти, чтобы это считалось перетаскиванием,
 *  а не щелчком. Пять точек — обычный порог: меньше ловит дрожание руки,
 *  больше начинает ощущаться как задержка. */
const DRAG_THRESHOLD_PX = 5;

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

interface Pending {
  row: RowMeta;
  siblings: RowMeta[];
  x: number;
  y: number;
  pointerId: number;
  target: HTMLElement;
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
  const pending = useRef<Pending | null>(null);
  // Щелчок приходит после отпускания и открыл бы правку той строки,
  // которую только что перетащили. Флаг живёт до этого щелчка и гасит его.
  const suppressClick = useRef(false);

  const begin = useCallback(() => {
    const armed = pending.current;
    if (!armed) return;
    armed.target.setPointerCapture?.(armed.pointerId);
    session.current = { row: armed.row, siblings: armed.siblings, targetIndex: armed.row.indexInDay };
    setDrag({ id: armed.row.transaction.id, targetIndex: armed.row.indexInDay });
  }, []);

  /**
   * Взяться за строку. Само перетаскивание начнётся позже — когда
   * указатель уйдёт с места, — если только не взялись за ручку:
   * за неё берутся именно ради перетаскивания, и ждать там нечего.
   */
  const arm = useCallback(
    (event: React.PointerEvent, row: RowMeta, siblings: RowMeta[], immediate = false) => {
      // Тащим только основной кнопкой или пальцем: правый клик и средняя
      // кнопка не должны начинать перетаскивание.
      if (event.button !== 0) return;
      // Единственную операцию дня переставлять некуда.
      if (siblings.length < 2) return;
      pending.current = {
        row,
        siblings,
        x: event.clientX,
        y: event.clientY,
        pointerId: event.pointerId,
        target: event.currentTarget as HTMLElement,
      };
      if (immediate) {
        event.preventDefault();
        begin();
      }
    },
    [begin]
  );

  const move = useCallback(
    (event: React.PointerEvent) => {
      const armed = pending.current;
      if (armed && !session.current) {
        const far =
          Math.abs(event.clientX - armed.x) > DRAG_THRESHOLD_PX ||
          Math.abs(event.clientY - armed.y) > DRAG_THRESHOLD_PX;
        if (!far) return;
        begin();
      }

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
    },
    [begin]
  );

  const end = useCallback(() => {
    const current = session.current;
    pending.current = null;
    session.current = null;
    setDrag(null);
    if (!current) return;
    // Даже перетаскивание, вернувшееся на исходное место, — не щелчок:
    // открывать правку после него человек не просил.
    suppressClick.current = true;
    if (current.targetIndex === current.row.indexInDay) return;
    onReorder(current.row.transaction, current.targetIndex, current.siblings.length);
  }, [onReorder]);

  /** Был ли перетаскиванием тот щелчок, который сейчас придёт. */
  const consumeClickSuppression = useCallback(() => {
    const suppressed = suppressClick.current;
    suppressClick.current = false;
    return suppressed;
  }, []);

  return { drag, arm, move, end, consumeClickSuppression };
}
