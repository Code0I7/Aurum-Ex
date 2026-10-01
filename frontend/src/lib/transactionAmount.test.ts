import { describe, expect, it } from "vitest";
import { amountColorClass, amountDirection, amountSign } from "@/lib/transactionAmount";

/**
 * Знак и цвет суммы операции.
 *
 * Эти три функции существуют потому, что развилка «плюс или минус» когда-то
 * повторялась в каждом списке отдельно и списки разошлись: подарок, отданный
 * человеку, показывался зелёным плюсом — деньги ушли, а выглядело как
 * заработок. Проверка здесь сторожит именно это: пять видов операций и
 * ровно три направления.
 */

describe("amountDirection", () => {
  it("заработок и полученное от человека — приход", () => {
    expect(amountDirection("income")).toBe("in");
    expect(amountDirection("external_in")).toBe("in");
  });

  it("трата и переданное человеку — расход", () => {
    // Вот та самая ошибка: external_out деньги со счёта уводит, и считать
    // его приходом «потому что это не expense» нельзя.
    expect(amountDirection("expense")).toBe("out");
    expect(amountDirection("external_out")).toBe("out");
  });

  it("перевод не двигает деньги никуда", () => {
    // Свои деньги переложены с одного счёта на другой: ни потери, ни
    // прибавления не произошло.
    expect(amountDirection("transfer")).toBe("none");
  });
});

describe("amountSign", () => {
  it("ставит плюс приходу и типографский минус расходу", () => {
    expect(amountSign("income")).toBe("+");
    expect(amountSign("external_in")).toBe("+");
    expect(amountSign("expense")).toBe("−");
    expect(amountSign("external_out")).toBe("−");
  });

  it("у перевода знака нет вовсе", () => {
    expect(amountSign("transfer")).toBe("");
  });

  it("минус именно типографский, а не дефис", () => {
    // В одном столбце с остальными суммами дефис короче минуса, и колонка
    // перестаёт выглядеть колонкой.
    expect(amountSign("expense")).toBe("−");
    expect(amountSign("expense")).not.toBe("-");
  });
});

describe("amountColorClass", () => {
  it("зелёный приходу, красный расходу", () => {
    expect(amountColorClass("income")).toBe("text-success");
    expect(amountColorClass("external_in")).toBe("text-success");
    expect(amountColorClass("expense")).toBe("text-danger");
    expect(amountColorClass("external_out")).toBe("text-danger");
  });

  it("перевод красится нейтрально, а не красным", () => {
    expect(amountColorClass("transfer")).toBe("text-text-muted");
  });

  it("нейтральный цвет можно заменить на пустой", () => {
    // В таблице строка уже окрашена целиком, и собственный серый у одной
    // колонки выбивался бы из ряда.
    expect(amountColorClass("transfer", "")).toBe("");
    // Остальным видам замена ничего не меняет.
    expect(amountColorClass("income", "")).toBe("text-success");
  });
});
