import { createContext, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Главное действие вкладки — в шапке приложения.
 *
 * Кнопка «Добавить» стояла в заголовке карточки, то есть в начале
 * страницы. На списке в месяц операций она уезжала вверх, и чтобы завести
 * ещё одну запись, приходилось прокручивать список обратно к началу.
 *
 * Шапка уже прилипшая, и справа от названия раздела у неё пусто. Поэтому
 * не «показывать кнопку в шапке, когда она пропала из виду» — это два
 * экземпляра одного элемента, слежение за видимостью и подскок при
 * появлении, — а просто одно место, где действие живёт всегда.
 *
 * Слот, а не кнопка транзакций в шапке: та же болезнь есть у счетов,
 * целей, товаров и всех прочих списков, и лечится она один раз.
 *
 * В слот уходит только **главное** действие. Импорт выписки и перенос
 * таблицы остаются на своей странице: они разовые, и три кнопки в шапке
 * вместо одной — это уже свалка.
 */
const SlotContext = createContext<{
  node: HTMLElement | null;
  setNode: (node: HTMLElement | null) => void;
}>({ node: null, setNode: () => {} });

export function PageActionsProvider({ children }: { children: ReactNode }) {
  // Узел шапки держится в состоянии, а не в ref: страница рисуется раньше,
  // чем ref заполнится, и портал без перерисовки просто не появился бы.
  const [node, setNode] = useState<HTMLElement | null>(null);
  return <SlotContext.Provider value={{ node, setNode }}>{children}</SlotContext.Provider>;
}

/** Место в шапке. Рисуется один раз — в Topbar. */
export function PageActionsOutlet({ className }: { className?: string }) {
  const { setNode } = useContext(SlotContext);
  return <div ref={setNode} className={className} />;
}

/**
 * Обёртка вокруг кнопки на странице: содержимое уезжает в шапку.
 *
 * Пока шапки нет (первая отрисовка), не показывает ничего — мигание
 * кнопкой на своём старом месте хуже её краткого отсутствия.
 */
export function PageActions({ children }: { children: ReactNode }) {
  const { node } = useContext(SlotContext);
  if (!node) return null;
  return createPortal(children, node);
}
