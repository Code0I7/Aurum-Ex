import { describe, expect, it } from "vitest";
import { ordinalEn, pluralEn, pluralRu } from "@/lib/plural";

/**
 * Склонение числительных.
 *
 * Проверять стоит потому, что ошибка здесь не ломает ничего, кроме
 * доверия: под подписью «каждые 2 неделя» стоит сумма, и к ней начинают
 * относиться так же, как к грамматике над ней.
 */

const DAYS = ["день", "дня", "дней"] as const;

describe("pluralRu", () => {
  it("берёт первую форму на единицу", () => {
    expect(pluralRu(1, DAYS)).toBe("день");
    expect(pluralRu(21, DAYS)).toBe("день");
    expect(pluralRu(101, DAYS)).toBe("день");
  });

  it("берёт вторую форму на два, три, четыре", () => {
    expect(pluralRu(2, DAYS)).toBe("дня");
    expect(pluralRu(3, DAYS)).toBe("дня");
    expect(pluralRu(4, DAYS)).toBe("дня");
    expect(pluralRu(22, DAYS)).toBe("дня");
    expect(pluralRu(104, DAYS)).toBe("дня");
  });

  it("берёт третью форму от пяти до двадцати", () => {
    expect(pluralRu(5, DAYS)).toBe("дней");
    expect(pluralRu(9, DAYS)).toBe("дней");
    expect(pluralRu(20, DAYS)).toBe("дней");
  });

  it("не путается на одиннадцати — четырнадцати", () => {
    // Главное исключение правила: по последней цифре здесь вышло бы
    // «одиннадцать день» и «двенадцать дня».
    expect(pluralRu(11, DAYS)).toBe("дней");
    expect(pluralRu(12, DAYS)).toBe("дней");
    expect(pluralRu(13, DAYS)).toBe("дней");
    expect(pluralRu(14, DAYS)).toBe("дней");
    expect(pluralRu(111, DAYS)).toBe("дней");
    expect(pluralRu(112, DAYS)).toBe("дней");
  });

  it("на нуле берёт третью форму", () => {
    expect(pluralRu(0, DAYS)).toBe("дней");
    expect(pluralRu(10, DAYS)).toBe("дней");
  });

  it("смотрит на величину, а не на знак", () => {
    // Отрицательные числа сюда приходят: «просрочено на 2 дня» считается
    // как разница дат и бывает со минусом.
    expect(pluralRu(-1, DAYS)).toBe("день");
    expect(pluralRu(-2, DAYS)).toBe("дня");
    expect(pluralRu(-11, DAYS)).toBe("дней");
  });
});

describe("pluralEn", () => {
  it("единственное только на единице", () => {
    expect(pluralEn(1, "day", "days")).toBe("day");
    expect(pluralEn(-1, "day", "days")).toBe("day");
  });

  it("множественное на всём остальном, включая ноль", () => {
    expect(pluralEn(0, "day", "days")).toBe("days");
    expect(pluralEn(2, "day", "days")).toBe("days");
    expect(pluralEn(21, "day", "days")).toBe("days");
  });
});

describe("ordinalEn", () => {
  it("раздаёт обычные окончания", () => {
    expect(ordinalEn(1)).toBe("1st");
    expect(ordinalEn(2)).toBe("2nd");
    expect(ordinalEn(3)).toBe("3rd");
    expect(ordinalEn(4)).toBe("4th");
    expect(ordinalEn(21)).toBe("21st");
    expect(ordinalEn(22)).toBe("22nd");
    expect(ordinalEn(23)).toBe("23rd");
  });

  it("не делает 11st, 12nd и 13rd", () => {
    expect(ordinalEn(11)).toBe("11th");
    expect(ordinalEn(12)).toBe("12th");
    expect(ordinalEn(13)).toBe("13th");
    expect(ordinalEn(111)).toBe("111th");
  });

  it("на нуле и прочих цифрах даёт th", () => {
    expect(ordinalEn(0)).toBe("0th");
    expect(ordinalEn(5)).toBe("5th");
    expect(ordinalEn(100)).toBe("100th");
  });
});
