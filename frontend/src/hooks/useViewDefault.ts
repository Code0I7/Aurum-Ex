import { useEffect, useRef, useState } from "react";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";

/**
 * Значение вида: сначала настройка с сервера, потом — выбор этого браузера.
 *
 * Два уровня, и они не спорят. Настройка в разделе «Настройки» отвечает на
 * вопрос «как открывать по умолчанию» и действует на всех устройствах:
 * установка однопользовательская, и выбор с ноутбука должен работать с
 * телефона. Переключатель на самой странице — временный, для этого экрана
 * и этого браузера.
 *
 * Пока настройки не загрузились, показывается серверное значение; как
 * только человек тронул переключатель, его выбор побеждает и запоминается
 * локально. Обратный порядок — «локальное всегда важнее» — означал бы, что
 * настройка по умолчанию не действует нигде, где человек однажды нажал
 * кнопку.
 */
export function useViewDefault<T>(storageKey: string, serverValue: T | undefined, fallback: T) {
  const [stored, setStored] = useLocalStorageState<T | null>(storageKey, null);
  const [value, setValue] = useState<T>(stored ?? serverValue ?? fallback);
  // Серверное значение применяется один раз: иначе повторная загрузка
  // настроек сбрасывала бы выбор, сделанный только что руками.
  const applied = useRef(stored !== null);

  useEffect(() => {
    if (applied.current || serverValue === undefined) return;
    applied.current = true;
    setValue(serverValue);
  }, [serverValue]);

  function change(next: T) {
    applied.current = true;
    setStored(next);
    setValue(next);
  }

  return [value, change] as const;
}
