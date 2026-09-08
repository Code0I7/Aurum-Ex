import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "aurum:theme";

const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

function readInitialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") return stored;
  return "system";
}

/** Светло или темно на самом деле: «системная» разворачивается в
 *  конкретную по настройке ОС. */
function resolve(theme: Theme): "light" | "dark" {
  return theme === "system" ? (darkQuery.matches ? "dark" : "light") : theme;
}

/**
 * Повторяет то, что делает встроенный скрипт в index.html при первой
 * загрузке, и вызывается заново на каждый setTheme — иначе переключение на
 * «системную» при тёмной ОС ждало бы перезагрузки страницы.
 *
 * Кроме `data-theme` проставляется `data-scheme` с уже разложенным
 * значением, и смотрят стили именно на него. Раньше тёмные значения
 * писались в CSS дважды: под `prefers-color-scheme` и под
 * `[data-theme="dark"]`. С появлением нескольких оформлений это дало бы
 * шесть почти одинаковых блоков вместо трёх, а расходятся такие копии
 * молча. Разложить тему один раз здесь дешевле: слушатель системной темы
 * всё равно нужен ради цвета адресной строки.
 */
function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", theme);
  }
  root.setAttribute("data-scheme", resolve(theme));

  // Цвет адресной строки берётся из вычисленного значения, а не из
  // константы: у каждого оформления полотно своё, и список их здесь
  // означал бы, что про четвёртое однажды забудут.
  const surface = getComputedStyle(root).getPropertyValue("--surface-0").trim();
  if (surface) document.querySelector('meta[name="theme-color"]')?.setAttribute("content", surface);
}

let currentTheme: Theme = readInitialTheme();
const listeners = new Set<() => void>();

darkQuery.addEventListener("change", () => {
  // Настройка ОС имеет значение только при «системной»: в остальных
  // случаях выбор человека главнее.
  if (currentTheme !== "system") return;
  applyTheme(currentTheme);
  listeners.forEach((listener) => listener());
});

export function getTheme(): Theme {
  return currentTheme;
}

export function setTheme(theme: Theme): void {
  if (theme === currentTheme) return;
  currentTheme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
  applyTheme(theme);
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, () => currentTheme);
  return { theme, setTheme };
}

/**
 * Тёмное ли оформление прямо сейчас.
 *
 * Нужно там, где выбирает разметка, а не CSS: фирменный знак — два
 * растровых файла, обсидиановый и мраморный, и подменить один другим
 * значением переменной нельзя.
 */
export function useIsDark(): boolean {
  return useSyncExternalStore(subscribe, () => resolve(currentTheme) === "dark");
}

// Первое применение при загрузке модуля. Атрибуты к этому моменту уже
// проставлены встроенным скриптом (до первой отрисовки), но цвет адресной
// строки он взять из стилей не мог — они тогда ещё не загрузились.
applyTheme(currentTheme);
