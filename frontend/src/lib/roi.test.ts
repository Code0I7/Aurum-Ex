import { describe, expect, it } from "vitest";
import { annualFromMonthly, calculateRoi, monthlyRate, type RoiInput } from "@/lib/roi";

/**
 * Калькулятор доходности.
 *
 * Здесь всё держится на одном решении: считать помесячно, а месячную ставку
 * брать как есть. Когда человек говорит «квартира приносит 5 000 в месяц»,
 * он имеет в виду ровно 5 000 в первый же месяц — и если свести это к
 * годовой ставке и вернуть обратно корнем, выйдет 4 744. Формально
 * правильно, а человек ввёл одно число и увидел другое.
 */

const BASE: RoiInput = {
  initial: 100000,
  payoutMonthlyRate: 0,
  growthRatePercent: 0,
  monthlyContribution: 0,
  contributionIndexPercent: 0,
  reinvestPayouts: false,
  years: 1,
};

describe("monthlyRate", () => {
  it("переводит годовую в месячную корнем, а не делением", () => {
    // Делением на 12 месячная ставка, начисленная двенадцать раз, даёт за
    // год больше заявленного, и расчёт незаметно завышает результат.
    const monthly = monthlyRate(12);
    expect(monthly).toBeLessThan(0.01);
    expect(Math.pow(1 + monthly, 12) - 1).toBeCloseTo(0.12, 10);
  });

  it("на нуле даёт ноль", () => {
    expect(monthlyRate(0)).toBe(0);
  });
});

describe("annualFromMonthly", () => {
  it("обратна переводу в месячную", () => {
    expect(annualFromMonthly(monthlyRate(12) * 100)).toBeCloseTo(12, 10);
  });

  it("один процент в месяц — это почти тринадцать в год", () => {
    // Сложный процент: именно этим подпись под полем ввода и полезна.
    expect(annualFromMonthly(1)).toBeCloseTo(12.6825, 3);
  });
});

describe("calculateRoi", () => {
  it("без доходности и довложений возвращает вложенное", () => {
    const result = calculateRoi(BASE);
    expect(result.total).toBeCloseTo(100000, 6);
    expect(result.contributed).toBe(100000);
    expect(result.earned).toBeCloseTo(0, 6);
  });

  it("первая выплата считается от стартовой суммы в первый же месяц", () => {
    // То самое: ввёл «5 000 в месяц» — увидел 5 000, а не 4 744.
    const result = calculateRoi({ ...BASE, payoutMonthlyRate: 0.05 });
    expect(result.firstMonthPayout).toBeCloseTo(5000, 6);
  });

  it("без реинвестирования выплаты копятся отдельно", () => {
    // Так считают те, кто живёт с дивидендов: капитал не растёт, а деньги
    // приходят.
    const result = calculateRoi({ ...BASE, payoutMonthlyRate: 0.01 });
    expect(result.years[0].capital).toBeCloseTo(100000, 6);
    expect(result.years[0].payoutsTotal).toBeCloseTo(12000, 6);
    expect(result.total).toBeCloseTo(112000, 6);
  });

  it("с реинвестированием выплаты работают сами", () => {
    const aside = calculateRoi({ ...BASE, payoutMonthlyRate: 0.01 });
    const reinvested = calculateRoi({ ...BASE, payoutMonthlyRate: 0.01, reinvestPayouts: true });
    expect(reinvested.total).toBeGreaterThan(aside.total);
    // Сложный процент за год: 1,01 в двенадцатой степени.
    expect(reinvested.total).toBeCloseTo(100000 * Math.pow(1.01, 12), 4);
  });

  it("довложения попадают во внесённое, а не в заработанное", () => {
    const result = calculateRoi({ ...BASE, monthlyContribution: 1000 });
    expect(result.contributed).toBe(112000);
    expect(result.earned).toBeCloseTo(0, 6);
  });

  it("довложение начинает работать со следующего месяца", () => {
    // Оно приходит в конце месяца: выплата этого месяца считается от
    // капитала на его начало, иначе деньги зарабатывали бы до внесения.
    const result = calculateRoi({ ...BASE, payoutMonthlyRate: 0.01, monthlyContribution: 1000 });
    expect(result.firstMonthPayout).toBeCloseTo(1000, 6);
  });

  it("индексация довложений применяется раз в год", () => {
    const result = calculateRoi({
      ...BASE,
      monthlyContribution: 1000,
      contributionIndexPercent: 10,
      years: 2,
    });
    // Первый год по 1 000, второй по 1 100.
    expect(result.years[0].contributed).toBe(112000);
    expect(result.years[1].contributed).toBeCloseTo(112000 + 13200, 6);
  });

  it("строка на каждый год, и годы нумеруются с единицы", () => {
    const result = calculateRoi({ ...BASE, years: 3 });
    expect(result.years.map((row) => row.year)).toEqual([1, 2, 3]);
  });

  it("окупаемость считается по живым выплатам", () => {
    // Вопрос «когда вернутся вложенные деньги» — про поступления, а не про
    // то, во что они успеют вырасти, поэтому реинвестирование её не меняет.
    const result = calculateRoi({ ...BASE, payoutMonthlyRate: 0.01, years: 20 });
    expect(result.paybackYears).toBeCloseTo(100000 / 12000, 6);
  });

  it("без выплат окупаемости нет вовсе", () => {
    // Null, а не бесконечность и не ноль: вопрос просто не имеет ответа.
    expect(calculateRoi(BASE).paybackYears).toBeNull();
  });

  it("рост стоимости актива идёт отдельно от выплат", () => {
    const result = calculateRoi({ ...BASE, growthRatePercent: 12 });
    expect(result.years[0].capital).toBeCloseTo(112000, 2);
    expect(result.years[0].payoutsTotal).toBe(0);
  });

  it("нулевой горизонт не выдумывает ни строк, ни денег", () => {
    const result = calculateRoi({ ...BASE, years: 0 });
    expect(result.years).toEqual([]);
    expect(result.total).toBe(100000);
  });
});
