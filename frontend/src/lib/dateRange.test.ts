import { describe, expect, it } from "vitest";
import { computeRange, defaultCustomRange } from "@/lib/dateRange";

/**
 * Период, за который считать.
 *
 * Выбор отсюда уходит прямо в запрос на сервер, и ошибка на день по краю
 * диапазона молча выбрасывает операции этого дня из итога. Заметно это
 * только тому, кто сверяет сумму вручную.
 */

describe("computeRange", () => {
  it("за всё время не ставит границ вовсе", () => {
    // Не «с 1970 года»: границ нет, и сервер сам берёт первую запись.
    expect(computeRange("all")).toEqual({});
  });

  it("этот год — с первого января по сегодня", () => {
    const today = new Date();
    const range = computeRange("this_year");
    expect(range.startDate).toBe(`${today.getFullYear()}-01-01`);
    expect(range.endDate).toBe(isoToday(today));
  });

  it("пять лет отсчитываются назад от начала текущего месяца", () => {
    const today = new Date();
    const range = computeRange("5y");
    const start = new Date(today.getFullYear() - 5, today.getMonth(), 1);
    expect(range.startDate).toBe(iso(start));
    expect(range.endDate).toBe(isoToday(today));
  });

  it("свой период отдаёт выбранные даты как есть", () => {
    // То, ради чего диапазон лет заменили датами: срез за три месяца
    // прошлого года раньше разворачивался в целые годы.
    expect(computeRange("custom", { from: "2024-03-01", to: "2024-05-31" })).toEqual({
      startDate: "2024-03-01",
      endDate: "2024-05-31",
    });
  });

  it("свой период без значения не ставит границ, а не пустые даты", () => {
    // Пустая строка в запросе — это не «без границы», а параметр, который
    // сервер попытается разобрать как дату.
    expect(computeRange("custom")).toEqual({});
  });

  it("один день — это один день, а не пустой диапазон", () => {
    expect(computeRange("custom", { from: "2025-05-14", to: "2025-05-14" })).toEqual({
      startDate: "2025-05-14",
      endDate: "2025-05-14",
    });
  });
});

describe("defaultCustomRange", () => {
  it("начинается с первого января и кончается сегодня", () => {
    const range = defaultCustomRange(new Date(2026, 9, 1));
    expect(range).toEqual({ from: "2026-01-01", to: "2026-10-01" });
  });

  it("не заканчивается в будущем", () => {
    // Раньше период по умолчанию кончался тридцать первым декабря, то есть
    // большую часть года обещал данные, которых ещё нет.
    const today = new Date(2026, 1, 3);
    expect(defaultCustomRange(today).to).toBe("2026-02-03");
  });

  it("собирает дату по местному времени, а не по UTC", () => {
    // toISOString переводит в UTC, и восточнее Гринвича ранним утром
    // возвращал вчерашний день — «по сегодня» теряло сегодняшние операции.
    const earlyMorning = new Date(2026, 2, 15, 1, 30);
    expect(defaultCustomRange(earlyMorning).to).toBe("2026-03-15");
  });

  it("добавляет ведущие нули в месяц и день", () => {
    expect(defaultCustomRange(new Date(2026, 0, 5)).to).toBe("2026-01-05");
  });
});

function iso(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function isoToday(today: Date): string {
  return iso(today);
}
