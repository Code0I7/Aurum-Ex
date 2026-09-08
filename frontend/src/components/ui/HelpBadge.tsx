import { useEffect, useRef, useState } from "react";
import { useTranslation, type TranslationKey } from "@/lib/i18n";

interface HelpBadgeProps {
  /** Ключ перевода с объяснением раздела. */
  hintKey: TranslationKey;
}

/**
 * Кружок с восклицательным знаком рядом с заголовком раздела.
 *
 * Приложение выросло из таблицы, где почти ничего из этого не было, и
 * половина вкладок отвечает на вопросы, которых человек себе раньше не
 * задавал. Объяснение должно лежать там, где возникает вопрос, — у названия
 * раздела, а не в отдельной справке, куда никто не пойдёт.
 *
 * Открывается по клику, а не по наведению: на телефоне наведения нет, а
 * дублировать подсказку двумя способами — это две реализации одного и того
 * же, расходящиеся при первой правке.
 */
export function HelpBadge({ hintKey }: HelpBadgeProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <span ref={container} className="relative inline-flex align-middle">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={t("help.what")}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-border text-[10px] font-bold leading-none text-text-muted transition-colors hover:border-text-secondary hover:text-text-primary"
      >
        !
      </button>

      {open && (
        // Ширина ограничена, а не тянется по содержимому: подсказка на всю
        // ширину экрана читается хуже колонки в сорок слов.
        <span
          role="tooltip"
          className="absolute left-0 top-6 z-30 w-72 max-w-[min(18rem,calc(100vw-2rem))] rounded-lg border border-border bg-surface-1 p-3 text-xs font-normal normal-case leading-relaxed tracking-normal text-text-secondary shadow-lg"
        >
          {t(hintKey)}
        </span>
      )}
    </span>
  );
}
