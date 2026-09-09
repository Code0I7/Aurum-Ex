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
 * И поэтому же палец за тело строки не берётся вовсе. Порог в пять точек
 * от случайного касания не спасает: обычный свайп прокрутки проходит его
 * мгновенно, и человек, листая список, незаметно для себя перемешивал
 * операции. Порядок операций — это данные, и терять их из-за жеста
 * прокрутки нельзя. Мышью тело строки тянется по-прежнему: там свайпа
 * прокрутки нет, а порог отсекает дрожание руки.
 *
 * Переставлять можно только внутри одного дня и одного счёта: день меняют
 * редактированием даты, а порядок операций разных счетов друг на друга не
 * влияет — у каждого своя нумерация.
 *
 * Тянется видимая строка, а не запись. Свёрнутая группа («Автобус ×4») —
 * это одна строка на экране и несколько записей в базе, и переносится она
 * целиком: по одной записи её двигать нельзя, потому что после первой же
 * перестановки нумерация меняется и остальные уезжают не туда.
 */

/** Насколько указатель должен уйти, чтобы это считалось перетаскиванием,
 *  а не щелчком. Пять точек — обычный порог: меньше ловит дрожание руки,
 *  больше начинает ощущаться как задержка. */
const DRAG_THRESHOLD_PX = 5;

export interface DragState {
  /** Ключ перетаскиваемой строки: операции или свёрнутой группы. */
  key: string;
  /** Визуальная позиция, на которую строка встанет, если отпустить сейчас. */
  targetIndex: number;
}

/** Видимая строка списка: одна операция или свёрнутая группа целиком. */
export interface DragUnit {
  key: string;
  /** Операции строки в порядке показа — от новых к старым. */
  items: Transaction[];
}

export interface RowMeta {
  unit: DragUnit;
  /** Позиция строки среди строк того же дня и счёта, сверху вниз. */
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
  onReorder: (row: RowMeta, visualIndex: number, siblings: RowMeta[]) => void
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
    setDrag({ key: armed.row.unit.key, targetIndex: armed.row.indexInDay });
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
      // Палец — только за ручку (immediate). См. рассуждение в шапке файла:
      // свайп прокрутки неотличим от начала перетаскивания, и список
      // перемешивался бы при обычном листании.
      if (event.pointerType === "touch" && !immediate) return;
      // Единственную строку дня переставлять некуда.
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
      const rowElement = element?.closest<HTMLElement>("[data-row-key]");
      if (!rowElement) return;

      const overKey = rowElement.dataset.rowKey;
      const over = current.siblings.find((item) => item.unit.key === overKey);
      // Строка другого дня или счёта — не цель: там своя нумерация.
      if (!over) return;

      if (over.indexInDay !== current.targetIndex) {
        current.targetIndex = over.indexInDay;
        setDrag({ key: current.row.unit.key, targetIndex: over.indexInDay });
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
    onReorder(current.row, current.targetIndex, current.siblings);
  }, [onReorder]);

  /** Был ли перетаскиванием тот щелчок, который сейчас придёт. */
  const consumeClickSuppression = useCallback(() => {
    const suppressed = suppressClick.current;
    suppressClick.current = false;
    return suppressed;
  }, []);

  return { drag, arm, move, end, consumeClickSuppression };
}
