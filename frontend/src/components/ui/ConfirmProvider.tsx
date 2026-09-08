import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { PropsWithChildren, ReactNode } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { useTranslation } from "@/lib/i18n";

export interface ConfirmOptions {
  /** Заголовок окна. По умолчанию — «Подтверждение». */
  title?: string;
  /** Вопрос. Переводы местами содержат перенос строки, поэтому текст
   *  выводится с сохранением разметки. */
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Красная кнопка для необратимого действия. */
  tone?: "danger" | "default";
  /** Только сообщение, без выбора, — замена window.alert. */
  acknowledgeOnly?: boolean;
}

type Ask = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<Ask | null>(null);

/**
 * Подтверждение действия окном приложения, а не окном браузера.
 *
 * `window.confirm` выглядит чужеродно, по-разному в каждом браузере, не
 * знает ни темы, ни шрифта приложения, а на телефоне прилетает системной
 * плашкой поверх всего. Хуже того, он блокирует поток: пока окно висит,
 * страница не перерисовывается.
 *
 * Обещание вместо колбэка — чтобы место вызова осталось прежним по форме:
 * `if (await confirm({...}))` читается так же, как `if (window.confirm(...))`,
 * и переписывать логику удаления в полутора десятках мест не пришлось.
 */
export function ConfirmProvider({ children }: PropsWithChildren) {
  const { t } = useTranslation();
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  // Ответ ждёт тот, кто спросил. Ссылка, а не состояние: перерисовка от
  // resolve не нужна, а терять его между рендерами нельзя.
  const resolveRef = useRef<((value: boolean) => void) | null>(null);

  const ask = useCallback<Ask>((next) => {
    return new Promise<boolean>((resolve) => {
      // Если предыдущий вопрос почему-то остался без ответа, закрываем его
      // отказом: висящее обещание — это навсегда заблокированный вызов.
      resolveRef.current?.(false);
      resolveRef.current = resolve;
      setOptions(next);
    });
  }, []);

  function settle(value: boolean) {
    const resolve = resolveRef.current;
    resolveRef.current = null;
    setOptions(null);
    resolve?.(value);
  }

  // Значение контекста стабильно: иначе каждая перерисовка провайдера
  // меняла бы `confirm` во всех потребителях и ломала бы их useCallback.
  const value = useMemo(() => ask, [ask]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      <Dialog
        open={options !== null}
        onClose={() => settle(false)}
        title={options?.title ?? t("common.confirmTitle")}
      >
        {/* whitespace-pre-line: часть вопросов состоит из двух абзацев —
            само действие и его последствие. */}
        <p className="whitespace-pre-line text-sm text-text-secondary">{options?.message}</p>
        <div className="mt-5 flex justify-end gap-2">
          {!options?.acknowledgeOnly && (
            <Button variant="ghost" onClick={() => settle(false)}>
              {options?.cancelLabel ?? t("common.cancel")}
            </Button>
          )}
          <Button
            variant={options?.tone === "danger" ? "danger" : "primary"}
            onClick={() => settle(true)}
            // Фокус на кнопке действия: Enter подтверждает, Escape
            // отменяет — как в системном окне, которое мы заменили.
            autoFocus
          >
            {options?.confirmLabel ?? t(options?.acknowledgeOnly ? "common.done" : "common.confirm")}
          </Button>
        </div>
      </Dialog>
    </ConfirmContext.Provider>
  );
}

/**
 * `const confirm = useConfirm()` → `if (await confirm({ message }))`.
 *
 * Вне провайдера падает намеренно: молчаливый откат к `window.confirm`
 * означал бы, что окно браузера иногда всё-таки появляется, и заметить это
 * можно было бы только случайно.
 */
export function useConfirm(): Ask {
  const ask = useContext(ConfirmContext);
  if (!ask) throw new Error("useConfirm must be used within ConfirmProvider");
  return ask;
}
