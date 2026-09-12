import type { PropsWithChildren, ReactNode } from "react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { layoutViewport } from "@/lib/scale";
import { useTranslation } from "@/lib/i18n";

interface DialogProps extends PropsWithChildren {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  /** Шире обычного — для форм, где в строке несколько полей. На телефоне
   *  ничего не меняет: там окно и так во всю ширину. */
  wide?: boolean;
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

export function Dialog({ open, onClose, title, wide, children }: DialogProps) {
  const { t } = useTranslation();
  const [available, setAvailable] = useState(visibleHeight);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  // Пересчёт на открытии и на любом изменении видимой области: поворот
  // телефона, появление клавиатуры, перетаскивание края окна браузера.
  useEffect(() => {
    if (!open) return;
    const update = () => setAvailable(visibleHeight());
    update();
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    return () => {
      window.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("resize", update);
    };
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
        "fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"
      )}
      onClick={onClose}
    >
      <div
        className={cn(
          "flex w-full flex-col rounded-t-2xl border border-border bg-surface-1 p-5 shadow-xl sm:rounded-2xl",
          wide ? "sm:max-w-[34rem]" : "sm:max-w-md"
        )}
        // Восемь процентов оставлено под отступ обёртки и полоску страницы
        // за краем окна: на телефоне окно выезжает снизу, и упёртое в самый
        // верх оно перестаёт читаться как окно.
        style={{ maxHeight: Math.max(available * 0.92, 200) }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex shrink-0 items-center justify-between">
          <h2 className="text-base font-semibold text-text-primary">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("common.close")}
            className="rounded-md p-1 text-text-muted hover:bg-surface-2"
          >
            <X size={18} />
          </button>
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
