import { useSyncExternalStore } from "react";

/**
 * Размер интерфейса — третья клиентская ось рядом с темой и оформлением.
 *
 * Хранится в localStorage, а НЕ в настройках на сервере, и это не экономия
 * на миграции. Размер — свойство экрана, на который смотрят, а не учётной
 * записи: телефон, ноутбук и монитор на стене хотят разного, и один и тот
 * же человек за день бывает у всех трёх. В localStorage он и так свой на
 * каждом устройстве — отдельной настройки «для телефона» и «для ПК» не
 * нужно, как и определения платформы, которое всё равно врёт на планшете и
 * на ноутбуке с сенсорным экраном.
 *
 * Применяется через `zoom`, а не через размер шрифта у корня. Размер шрифта
 * растянул бы только то, что задано в rem: отступы и текст выросли бы, а
 * значки, которым размер задан в точках, остались бы прежними — при 200%
 * это выглядит как интерфейс с булавочными головками вместо иконок. `zoom`
 * увеличивает всё разом и заставляет раскладку перестроиться, в отличие от
 * `transform: scale`, который просто растягивает картинку вместе с
 * полосами прокрутки.
 */
export type Scale = 100 | 125 | 150 | 200 | 300;

/** 125 добавлен к перечисленным: шаг со 100 сразу на 150 великоват, а
 *  промежуточный — самый ходовой на ноутбуке с мелким экраном. */
export const SCALES: Scale[] = [100, 125, 150, 200, 300];

const STORAGE_KEY = "aurum:scale";
const DEFAULT: Scale = 100;

function readInitial(): Scale {
  try {
    const stored = Number(localStorage.getItem(STORAGE_KEY));
    return SCALES.includes(stored as Scale) ? (stored as Scale) : DEFAULT;
  } catch {
    // Приватное окно или отключённое хранилище: падать из-за масштаба
    // приложение не должно.
    return DEFAULT;
  }
}

function apply(scale: Scale): void {
  // Сотня — это «как было»: свойство снимается совсем, чтобы у обычного
  // случая не оставалось лишнего слоя, который может на что-то влиять.
  const root = document.documentElement;
  if (scale === DEFAULT) root.style.removeProperty("zoom");
  else root.style.setProperty("zoom", String(scale / 100));
  applyViewportSize();
}

let current: Scale = readInitial();
const listeners = new Set<() => void>();

export function setScale(scale: Scale): void {
  if (scale === current) return;
  current = scale;
  try {
    localStorage.setItem(STORAGE_KEY, String(scale));
  } catch {
    // Не сохранилось — масштаб всё равно применится до перезагрузки.
  }
  apply(scale);
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useScale() {
  const scale = useSyncExternalStore(subscribe, () => current);
  return { scale, setScale };
}

/**
 * Во сколько раз увеличен интерфейс. Нужен там, где координаты с экрана
 * встречаются с координатами разметки.
 *
 * getBoundingClientRect() возвращает пиксели экрана — уже увеличенные. А
 * элемент с `position: fixed` лежит внутри увеличенного корня, и его `top`
 * и `left` считаются в неувеличенных. Подставить одно в другое значит
 * промахнуться ровно во столько раз, во сколько увеличен интерфейс: при
 * 150% выпадающий список уезжал вбок примерно на половину своего отступа
 * от края, и чем дальше поле от левого верхнего угла, тем сильнее.
 */
export function currentZoom(): number {
  return current / 100;
}

/**
 * Видимая часть страницы в единицах разметки.
 *
 * Деление на масштаб живёт здесь одно на всех: из окна всё приходит в
 * экранных пикселях (innerWidth, visualViewport, getBoundingClientRect), а
 * ставится потом в разметочных — в `top`, в `left`, в `max-height`. Каждое
 * место, где это делалось само по себе, рано или поздно оказывалось тем
 * местом, где про деление забыли.
 *
 * visualViewport вместо окна там, где он есть: на телефоне он уменьшается
 * на высоту клавиатуры, и «видимое» перестаёт означать «спрятанное под
 * ней». `top` — насколько видимая часть сдвинута вниз: у fixed-элемента
 * отсчёт от неё, а не от окна.
 */
export function layoutViewport(): { top: number; width: number; height: number } {
  const zoom = currentZoom();
  const view = window.visualViewport;
  return {
    top: (view?.offsetTop ?? 0) / zoom,
    width: (view?.width ?? window.innerWidth) / zoom,
    height: (view?.height ?? window.innerHeight) / zoom,
  };
}

/**
 * Те же размеры для разметки: `--app-vw` и `--app-vh`.
 *
 * `vw` и `vh` для этого не годятся. Они считаются от экрана и про
 * увеличение ничего не знают, а применяются внутри увеличенного корня — и
 * умножаются на масштаб второй раз. «50vh» при 150% занимает три четверти
 * экрана, при 300% — полтора экрана. Запасные значения стоят в index.css:
 * при обычном масштабе они и есть верные.
 */
function applyViewportSize(): void {
  const { width, height } = layoutViewport();
  const root = document.documentElement;
  root.style.setProperty("--app-vw", `${width}px`);
  root.style.setProperty("--app-vh", `${height}px`);
}

// Размер окна меняется и без участия масштаба: поворот телефона, край окна
// браузера, выехавшая клавиатура. Последняя не вызывает ни resize окна, ни
// прокрутку — только своё событие у видимой части.
window.addEventListener("resize", applyViewportSize);
window.visualViewport?.addEventListener("resize", applyViewportSize);

apply(current);
