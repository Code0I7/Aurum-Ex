import type { PropsWithChildren, ReactNode } from "react";
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";

interface DialogProps extends PropsWithChildren {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  /** Шире обычного — для форм, где в строке несколько полей. На телефоне
   *  ничего не меняет: там окно и так во всю ширину. */
  wide?: boolean;
}

export function Dialog({ open, onClose, title, wide, children }: DialogProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

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
          "max-h-[90vh] w-full overflow-y-auto rounded-t-2xl border border-border bg-surface-1 p-5 shadow-xl sm:rounded-2xl",
          wide ? "sm:max-w-[34rem]" : "sm:max-w-md"
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
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
        {children}
      </div>
    </div>,
    document.body
  );
}
