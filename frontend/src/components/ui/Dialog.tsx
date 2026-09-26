import type { PropsWithChildren, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Eye, Pin, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { currentZoom, layoutViewport } from "@/lib/scale";
import { useSessionState } from "@/hooks/useSessionState";
import { useTranslation } from "@/lib/i18n";

interface DialogProps extends PropsWithChildren {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  /** Шире обычного — для форм, где в строке несколько полей. На телефоне
   *  ничего не меняет: там окно и так во всю ширину. */
  wide?: boolean;
  /**
   * Под каким именем помнить место окна и замок до конца сеанса.
   *
   * Нужно там, где окно открывают много раз подряд и каждый раз по одному и
   * тому же делу: правка операций идёт одна за другой, и отодвигать окно
   * заново на каждую — работа вместо работы. Остальные окна двигаются так
   * же, но открываются снова по центру: место, выбранное для разового
   * вопроса, помнить незачем.
   */
  positionKey?: string;
}

/** Куда сдвинуто окно и закреплено ли оно. */
interface Placement {
  dx: number;
  dy: number;
  pinned: boolean;
}

const CENTERED: Placement = { dx: 0, dy: 0, pinned: false };

/** Отступ от краёв экрана, за который окно не уезжает. */
const EDGE_MARGIN = 8;
/** Сколько окна обязано остаться на виду снизу: шапка с крестиком. Иначе
 *  окно можно утащить за нижний край и не найти, чем его закрыть. */
const HEADER_VISIBLE = 56;
/** С какой ширины окно можно двигать. Ниже — телефон: там окно во всю
 *  ширину и выезжает снизу, двигать его некуда. */
const MOVABLE_FROM = 640;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

/**
 * Высота видимой части страницы — в тех единицах, в которых заданы размеры
 * внутри окна.
 *
 * `vh` для этого не годится. При увеличенном интерфейсе корень растянут
 * через `zoom`, и «90vh» означает 90% экрана, умноженные на масштаб: при
 * 150% окно выходит выше экрана в полтора раза. Кнопка «Сохранить» уезжала
 * за нижний край, и добраться до неё было нельзя — прокрутка внутри окна не
 * помогает, когда за край экрана ушёл сам прокручиваемый блок. Заметно это
 * становилось на длинной форме: несколько категорий в операции, и кнопки
 * уже нет.
 *
 * visualViewport вместо innerHeight там, где он есть: на телефоне он
 * уменьшается на высоту клавиатуры, и окно перестаёт прятать под ней свои
 * же кнопки.
 */
function visibleHeight(): number {
  return layoutViewport().height;
}

/**
 * Место окна: на сеанс — для окон с именем, на одно открытие — для всех
 * остальных.
 *
 * Оба состояния объявлены всегда, а выбор между ними — уже в возвращаемом
 * значении: хуки нельзя вызывать по условию, иначе их порядок между
 * отрисовками разъедется.
 */
function useDialogPlacement(
  positionKey: string | undefined
): readonly [Placement, (next: Placement | ((previous: Placement) => Placement)) => void] {
  const stored = useSessionState<Placement>(`aurum:dialog-${positionKey ?? "unnamed"}`, CENTERED);
  const [transient, setTransient] = useState<Placement>(CENTERED);
  return positionKey ? stored : [transient, setTransient];
}

export function Dialog({ open, onClose, title, wide, positionKey, children }: DialogProps) {
  const { t } = useTranslation();
  const [available, setAvailable] = useState(visibleHeight);
  // Двигать окно есть смысл только там, где вокруг него остаётся место.
  const [movable, setMovable] = useState(() => layoutViewport().width >= MOVABLE_FROM);
  const [placement, setPlacement] = useDialogPlacement(positionKey);
  // Пока кнопка-глаз нажата, окно почти исчезает и затемнение снимается:
  // список под ним виден целиком и читается. Постоянная полупрозрачность
  // тут не годится — текст поверх текста не читается ни в одном слое, а под
  // окном как раз суммы, в которых ошибка незаметна.
  const [peeking, setPeeking] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    dx: number;
    dy: number;
    minDx: number;
    maxDx: number;
    minDy: number;
    maxDy: number;
  } | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  // Подсматривание кончается вместе с открытием: окно, открытое прозрачным,
  // читалось бы как поломанное.
  useEffect(() => {
    if (!open) setPeeking(false);
  }, [open]);

  // Пересчёт на открытии и на любом изменении видимой области: поворот
  // телефона, появление клавиатуры, перетаскивание края окна браузера.
  useEffect(() => {
    if (!open) return;
    const update = () => {
      const view = layoutViewport();
      setAvailable(view.height);
      setMovable(view.width >= MOVABLE_FROM);
      // Сдвинутое окно после уменьшения экрана может оказаться за его
      // краем — тогда оно возвращается в середину. Пока оно на виду,
      // выбранное место сохраняется: браузер меняют в размерах и просто
      // так, и сбрасывать из-за этого расстановку было бы навязчиво.
      const box = boxRef.current;
      if (!box) return;
      const zoom = currentZoom();
      const rect = box.getBoundingClientRect();
      const offScreen =
        rect.left / zoom < 0 ||
        rect.right / zoom > view.width ||
        rect.top / zoom < view.top ||
        rect.top / zoom > view.top + view.height - HEADER_VISIBLE;
      if (offScreen) setPlacement((previous) => ({ ...previous, dx: 0, dy: 0 }));
    };
    update();
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    return () => {
      window.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("resize", update);
    };
    // setPlacement пересоздаётся на каждой отрисовке, но внутри держит
    // стабильный setState — подписка переживает это без переподписки.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Пока окно открыто, страница под ним не прокручивается. Иначе колесо
  // мыши над затемнением уводит список на сотню строк вниз, и после
  // закрытия человек оказывается неизвестно где.
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  if (!open) return null;

  const draggable = movable && !placement.pinned;

  /**
   * Начало перетаскивания за шапку.
   *
   * Границы считаются один раз здесь, а не на каждом движении: они зависят
   * от того, где окно стояло до сдвига, и пересчитывать это на ходу значит
   * ловить собственный же сдвиг. Всё в единицах разметки — из окна размеры
   * приходят в экранных, а ставится потом сдвиг в разметочных (см.
   * lib/scale).
   */
  function startDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (!draggable) return;
    // Кнопки в шапке тянуть не должны: крестик, глаз и замок нажимают, а не
    // тащат.
    if ((event.target as HTMLElement).closest("button")) return;
    const box = boxRef.current;
    if (!box) return;
    const zoom = currentZoom();
    const rect = box.getBoundingClientRect();
    const view = layoutViewport();
    const naturalLeft = rect.left / zoom - placement.dx;
    const naturalTop = rect.top / zoom - placement.dy;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      dx: placement.dx,
      dy: placement.dy,
      minDx: EDGE_MARGIN - naturalLeft,
      maxDx: view.width - EDGE_MARGIN - naturalLeft - rect.width / zoom,
      minDy: view.top + EDGE_MARGIN - naturalTop,
      maxDy: view.top + view.height - HEADER_VISIBLE - naturalTop,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function continueDrag(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const zoom = currentZoom();
    const dx = clamp(drag.dx + (event.clientX - drag.startX) / zoom, drag.minDx, drag.maxDx);
    const dy = clamp(drag.dy + (event.clientY - drag.startY) / zoom, drag.minDy, drag.maxDy);
    setPlacement((previous) => ({ ...previous, dx, dy }));
  }

  function endDrag() {
    dragRef.current = null;
  }

  /*
   * Окно рисуется в <body>, а не там, где стоит в разметке.
   *
   * `position: fixed` отсчитывается от экрана только до тех пор, пока ни
   * у одного предка нет transform, filter или containment: любой из них
   * делает предка точкой отсчёта, и «на весь экран» превращается в «на всю
   * карточку». Так и вышло — окно правки открывалось где-то посреди
   * страницы, а при сотне загруженных строк уезжало за её пределы.
   *
   * Ловить это по одному предку бессмысленно: их много и появляются новые
   * (приподнимание карточки под курсором в «современном» оформлении,
   * приглушение цвета у графиков). Портал снимает вопрос целиком —
   * предков между окном и <body> просто не остаётся.
   */
  return createPortal(
    <div
      className={cn(
        "fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4",
        peeking ? "bg-transparent" : "bg-black/40"
      )}
      onClick={onClose}
    >
      <div
        ref={boxRef}
        className={cn(
          "flex w-full flex-col rounded-t-2xl border border-border bg-surface-1 p-5 shadow-xl transition-opacity sm:rounded-2xl",
          wide ? "sm:max-w-[34rem]" : "sm:max-w-md",
          peeking && "opacity-[0.07]"
        )}
        style={{
          // Восемь процентов оставлено под отступ обёртки и полоску страницы
          // за краем окна: на телефоне окно выезжает снизу, и упёртое в самый
          // верх оно перестаёт читаться как окно.
          maxHeight: Math.max(available * 0.92, 200),
          // Сдвиг переносом, а не полями: перенос не влияет на разметку
          // вокруг и не заставляет пересчитывать её на каждое движение мыши.
          transform:
            placement.dx || placement.dy
              ? `translate(${placement.dx}px, ${placement.dy}px)`
              : undefined,
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          className={cn(
            "mb-4 flex shrink-0 items-center justify-between gap-2",
            draggable && "cursor-move select-none"
          )}
          // Палец на планшете иначе прокручивал бы страницу под окном
          // вместо перетаскивания.
          style={draggable ? { touchAction: "none" } : undefined}
          onPointerDown={startDrag}
          onPointerMove={continueDrag}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          <h2 className="min-w-0 text-base font-semibold text-text-primary">{title}</h2>
          <span className="flex shrink-0 items-center gap-0.5">
            {/* Глаз без подписи: место в шапке занимает название окна, а
                держать кнопку и читать её подпись всё равно нельзя
                одновременно. */}
            <button
              type="button"
              aria-label={t("common.peek")}
              title={t("common.peek")}
              onPointerDown={(event) => {
                // Захват указателя: окно под пальцем становится почти
                // невидимым, и без захвата «отпустил» ушло бы неизвестно
                // куда, а окно осталось бы прозрачным.
                event.currentTarget.setPointerCapture(event.pointerId);
                setPeeking(true);
              }}
              onPointerUp={() => setPeeking(false)}
              onPointerCancel={() => setPeeking(false)}
              onLostPointerCapture={() => setPeeking(false)}
              className="rounded-md p-1 text-text-muted hover:bg-surface-2"
            >
              <Eye size={17} />
            </button>
            {/* Кнопка-гвоздик — от случайного сдвига: шапку задевают мышью,
                когда тянутся к крестику. Приколотое окно остаётся на своём
                месте, в том числе на следующем открытии.

                Отжатая нарисована контуром, нажатая залита — как настоящая
                кнопка, вдавленная в лист. Два разных значка («кнопка» и
                «кнопка зачёркнута») читались бы как «приколоть» и «прокол
                запрещён», а состояние здесь одно и то же, только нажатое. */}
            {movable && (
              <button
                type="button"
                aria-label={t(placement.pinned ? "common.unpinWindow" : "common.pinWindow")}
                title={t(placement.pinned ? "common.unpinWindow" : "common.pinWindow")}
                onClick={() => setPlacement((previous) => ({ ...previous, pinned: !previous.pinned }))}
                className={cn(
                  "rounded-md p-1 hover:bg-surface-2",
                  placement.pinned ? "text-accent" : "text-text-muted"
                )}
              >
                <Pin size={17} fill={placement.pinned ? "currentColor" : "none"} />
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label={t("common.close")}
              className="rounded-md p-1 text-text-muted hover:bg-surface-2"
            >
              <X size={18} />
            </button>
          </span>
        </div>
        {/* Прокручивается только содержимое: заголовок и крестик остаются на
            месте. Раньше прокручивалось окно целиком, и у длинной формы
            крестик уезжал вверх — закрыть её можно было только щелчком по
            затемнению, о котором никто не догадывается.

            Отрицательные поля с обратным отступом внутри: полоса прокрутки
            встаёт у самого края окна, а содержимое сохраняет свой отступ. */}
        <div className="-mx-5 min-h-0 flex-1 overflow-y-auto px-5">{children}</div>
      </div>
    </div>,
    document.body
  );
}
