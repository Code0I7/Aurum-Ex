import { useState } from "react";

/**
 * Значение, живущее до закрытия вкладки, но переживающее переходы между
 * разделами.
 *
 * Отличается от useLocalStorageState тем, откуда оно возвращается и когда
 * забывается. Раскладка колонок — настройка: она должна пережить и
 * перезагрузку, и завтрашний день. А выбранный месяц — не настройка, а
 * место, где человек сейчас находится: возвращать его через неделю
 * значило бы открывать приложение в прошлом.
 *
 * Между этими двумя крайностями и есть сеанс. Ушёл в отчёты, вернулся в
 * операции — тот же месяц, те же фильтры. Закрыл вкладку — приложение
 * снова открывается на текущем месяце.
 *
 * Чтение и запись обёрнуты в try/catch: в приватном окне и при
 * отключённом хранилище обращение бросает исключение, и падать из-за
 * запомненного месяца приложение не должно. Битый JSON уступает место
 * значению по умолчанию там же.
 */
export function useSessionState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = sessionStorage.getItem(key);
      if (stored === null) return initial;
      return JSON.parse(stored) as T;
    } catch {
      return initial;
    }
  });

  // Принимает и значение, и функцию от предыдущего — как обычный
  // useState. Без этого `setPage((p) => p + 1)` молча записал бы в
  // состояние саму функцию, и страница стала бы «[object Function]».
  const update = (next: T | ((previous: T) => T)) => {
    setValue((previous) => {
      const resolved = typeof next === "function" ? (next as (value: T) => T)(previous) : next;
      try {
        sessionStorage.setItem(key, JSON.stringify(resolved));
      } catch {
        // Хранилище недоступно — значение доживёт до ухода со страницы в памяти.
      }
      return resolved;
    });
  };

  return [value, update] as const;
}
