import { useSyncExternalStore } from "react";

/**
 * Оформление — вторая ось рядом с темой.
 *
 * Тема отвечает на вопрос «светло или темно», оформление — «в каком
 * характере». Это разные вопросы: человек, выбравший тёмное, не обязан
 * выбирать вместе с ним и золото. Поэтому два независимых атрибута на
 * <html>, а не шесть готовых тем в одном списке.
 *
 * Добавить своё оформление — это одна строка здесь и один блок переменных
 * в index.css под тем же именем. Больше ничего трогать не нужно: цвета
 * приложение берёт только из переменных, а `data-design` их и переключает.
 */
export type Design = "gold" | "modern" | "legacy";

/** Порядок в настройках. Legacy последним намеренно: это оформление,
 *  доставшееся от оригинального Aurum, и оно здесь ради возврата, а не как
 *  предложение по умолчанию. */
export const DESIGNS: Design[] = ["gold", "modern", "legacy"];

const STORAGE_KEY = "aurum:design";
const DEFAULT: Design = "gold";

function readInitial(): Design {
  const stored = localStorage.getItem(STORAGE_KEY);
  return DESIGNS.includes(stored as Design) ? (stored as Design) : DEFAULT;
}

function apply(design: Design): void {
  document.documentElement.setAttribute("data-design", design);
  // Полотно у оформлений разное, и адресная строка на телефоне должна
  // совпадать с ним, иначе сверху остаётся полоска чужого цвета.
  const surface = getComputedStyle(document.documentElement).getPropertyValue("--surface-0").trim();
  if (surface) document.querySelector('meta[name="theme-color"]')?.setAttribute("content", surface);
}

let current: Design = readInitial();
const listeners = new Set<() => void>();

export function setDesign(design: Design): void {
  if (design === current) return;
  current = design;
  localStorage.setItem(STORAGE_KEY, design);
  apply(design);
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useDesign() {
  const design = useSyncExternalStore(subscribe, () => current);
  return { design, setDesign };
}

apply(current);
