import { describe, expect, it } from "vitest";
import {
  DEFAULT_RECURRENCE,
  PRESETS,
  presetOf,
  recurrenceOfPreset,
  type Recurrence,
} from "@/lib/recurrence";

/**
 * Расписание плана.
 *
 * Самое неприятное место формы планов: уточнения у пунктов разные, и
 * оставшееся от прошлого выбора поле сервер не примет. Отказ при сохранении
 * тогда указывает на поле, которого человек уже не видит.
 *
 * Поэтому проверяется два свойства: пункт списка узнаётся по сохранённому
 * правилу, и переход на другой пункт не тащит за собой чужие уточнения.
 */

describe("presetOf", () => {
  it("узнаёт простые пункты", () => {
    expect(presetOf({ ...DEFAULT_RECURRENCE, kind: "one_off" })).toBe("once");
    expect(presetOf({ ...DEFAULT_RECURRENCE, kind: "day" })).toBe("daily");
    expect(presetOf({ ...DEFAULT_RECURRENCE, kind: "week" })).toBe("weekly");
    expect(presetOf({ ...DEFAULT_RECURRENCE, kind: "month" })).toBe("monthly");
    expect(presetOf({ ...DEFAULT_RECURRENCE, kind: "year" })).toBe("yearly");
  });

  it("ежедневный план с пропуском выходных — это «по рабочим»", () => {
    expect(presetOf({ ...DEFAULT_RECURRENCE, kind: "day", skip_weekends: true })).toBe("workday");
  });

  it("любой шаг кроме единицы — это «произвольно»", () => {
    // «Каждые две недели» в список пунктов не влезает, и честнее открыть
    // форму на произвольном правиле, чем показать «еженедельно» и соврать.
    expect(presetOf({ ...DEFAULT_RECURRENCE, kind: "week", repeat_every: 2 })).toBe("custom");
    expect(presetOf({ ...DEFAULT_RECURRENCE, kind: "month", repeat_every: 3 })).toBe("custom");
  });

  it("разовый план остаётся разовым при любом шаге", () => {
    // У «один раз» шага нет по смыслу, и наткнуться на «произвольно»
    // из-за случайного значения в поле он не должен.
    expect(presetOf({ ...DEFAULT_RECURRENCE, kind: "one_off", repeat_every: 5 })).toBe("once");
  });
});

describe("recurrenceOfPreset", () => {
  const WEEKLY: Recurrence = {
    ...DEFAULT_RECURRENCE,
    kind: "week",
    weekdays: [0, 3],
    month_days: [15],
    nth_weekday: 2,
  };

  it("сбрасывает уточнения, которые к новому пункту не относятся", () => {
    // Дни месяца, оставшиеся от «ежемесячно», в недельном плане ничего не
    // значат, и сервер такой план не примет.
    const monthly = recurrenceOfPreset("monthly", WEEKLY);
    expect(monthly.kind).toBe("month");
    expect(monthly.weekdays).toBeNull();
    expect(monthly.month_days).toBeNull();
    expect(monthly.nth_weekday).toBeNull();
  });

  it("возвращает шаг к единице", () => {
    const monthly = recurrenceOfPreset("monthly", { ...WEEKLY, repeat_every: 4 });
    expect(monthly.repeat_every).toBe(1);
  });

  it("дни недели переживают возврат к «еженедельно»", () => {
    // Единственное уточнение, которое к этому пункту и относится: терять
    // его при случайном переключении туда-обратно незачем.
    expect(recurrenceOfPreset("weekly", WEEKLY).weekdays).toEqual([0, 3]);
  });

  it("«по отработанным дням» переживает возврат к «ежедневно»", () => {
    // Это про тот же самый ежедневный план, а не про другое расписание.
    const previous = { ...DEFAULT_RECURRENCE, kind: "day" as const, workdays_only: true };
    expect(recurrenceOfPreset("daily", previous).workdays_only).toBe(true);
  });

  it("«по рабочим» ставит пропуск выходных, а «ежедневно» — снимает", () => {
    expect(recurrenceOfPreset("workday", DEFAULT_RECURRENCE).skip_weekends).toBe(true);
    const back = recurrenceOfPreset("daily", { ...DEFAULT_RECURRENCE, skip_weekends: true });
    expect(back.skip_weekends).toBe(false);
  });

  it("«произвольно» сохраняет уже выбранное", () => {
    // Сюда переходят, чтобы дописать шаг, а не чтобы начать заново.
    const custom = recurrenceOfPreset("custom", WEEKLY);
    expect(custom.kind).toBe("week");
    expect(custom.weekdays).toEqual([0, 3]);
  });

  it("«произвольно» из разового даёт месячный, а не разовый с шагом", () => {
    // «Один раз каждые три месяца» — противоречие: разовый план повторять
    // нечем.
    const custom = recurrenceOfPreset("custom", { ...DEFAULT_RECURRENCE, kind: "one_off" });
    expect(custom.kind).toBe("month");
  });

  it("каждый готовый пункт узнаёт сам себя обратно", () => {
    // Круговая проверка: пункт -> правило -> пункт. Если расходится, форма
    // при открытии показывает не тот пункт, который сохраняли.
    //
    // «Произвольно» в проверку не входит намеренно: это не отдельное
    // расписание, а то же правило с шагом, который человек сейчас
    // напечатает. Пока шаг равен единице, оно и должно узнаваться как
    // готовый пункт — иначе «каждый 1 месяц» открывалось бы произвольным
    // вместо «ежемесячно».
    for (const preset of PRESETS.filter((value) => value !== "custom")) {
      expect(presetOf(recurrenceOfPreset(preset, DEFAULT_RECURRENCE))).toBe(preset);
    }
    expect(presetOf(recurrenceOfPreset("custom", DEFAULT_RECURRENCE))).toBe("monthly");
  });
});
