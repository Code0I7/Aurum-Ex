import { useState } from "react";

/**
 * Значение, переживающее перезагрузку страницы.
 *
 * Раньше умел только булев флаг (свёрнуто ли меню). Теперь хранит любое
 * значение, сериализуемое в JSON, — это понадобилось раскладке колонок
 * таблицы транзакций: человек настраивает её под себя один раз, и
 * возвращать таблицу к умолчанию на каждый заход значило бы обесценить саму
 * настройку.
 *
 * Чтение и запись обёрнуты в try/catch: в приватном окне и при отключённом
 * хранилище обращение к localStorage бросает исключение, и падать из-за
 * свёрнутого меню приложение не должно. Разбор битого JSON — там же:
 * повреждённая запись просто уступает место значению по умолчанию.
 */
export function useLocalStorageState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(key);
      if (stored === null) return initial;
      // Прежние версии хранили булево значение голым словом "true"/"false",
      // без кавычек, — JSON.parse его разберёт, так что старые записи
      // продолжают работать без миграции.
      return JSON.parse(stored) as T;
    } catch {
      return initial;
    }
  });

  const update = (next: T) => {
    setValue(next);
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {
      // Хранилище недоступно — значение доживёт до перезагрузки в памяти.
    }
  };

  return [value, update] as const;
}
