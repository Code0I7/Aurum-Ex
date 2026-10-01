import { beforeEach, describe, expect, it } from "vitest";
import {
  formatCryptoAmount,
  formatCurrency,
  formatQuantity,
  getIntlLocale,
  maskAmount,
  trimTrailingZeros,
} from "@/lib/format";
import { setCurrency, setLanguage, setShowCents } from "@/lib/i18n";

/**
 * Показ сумм.
 *
 * Проверяется не вид подписи, а то, что число доходит до экрана целым:
 * округление, потерянный знак и неразобранный хвост нулей здесь выглядят
 * как ошибка расчёта, хотя расчёт верен.
 *
 * Пробелы в сравнениях нормализуются: Intl ставит между числом и значком
 * неразрывный либо узкий неразрывный пробел, и какой именно — свойство
 * версии ICU, а не поведения приложения.
 */
function spaces(value: string): string {
  return value.replace(/[   ]/g, " ");
}

beforeEach(() => {
  setLanguage("ru");
  setCurrency("RUB");
  setShowCents(true);
});

describe("getIntlLocale", () => {
  it("сопоставляет язык установки с локалью Intl", () => {
    expect(getIntlLocale("ru")).toBe("ru-RU");
    expect(getIntlLocale("en")).toBe("en-US");
  });
});

describe("formatCurrency", () => {
  it("печатает сумму со значком валюты", () => {
    expect(spaces(formatCurrency(1234.56))).toBe("1 234,56 ₽");
  });

  it("принимает строку так же, как число", () => {
    // Сервер отдаёт денежные поля строками, чтобы не терять точность, и до
    // форматирования они доходят как есть.
    expect(spaces(formatCurrency("1234.56"))).toBe(spaces(formatCurrency(1234.56)));
  });

  it("подчиняется настройке «точное отображение»", () => {
    // Копейки в операции — это данные: 36,99, показанные как 37, уже не то,
    // что записано, и столбец из таких строк не сходится в сумму.
    setShowCents(false);
    expect(spaces(formatCurrency(36.99))).toBe("37 ₽");
    setShowCents(true);
    expect(spaces(formatCurrency(36.99))).toBe("36,99 ₽");
  });

  it("берёт валюту установки, когда её не передали", () => {
    setCurrency("USD");
    expect(formatCurrency(10)).toContain("$");
  });

  it("не падает на пустой валюте, а показывает сумму в валюте установки", () => {
    // Intl на пустой код отвечает исключением, и вкладка «Капитал» так и
    // падала: валюта приходит из ответа сервера, а до ответа её нет.
    expect(spaces(formatCurrency(100, ""))).toBe(spaces(formatCurrency(100)));
    expect(spaces(formatCurrency(100, "   "))).toBe(spaces(formatCurrency(100)));
  });

  it("печатает чужую валюту, когда она указана", () => {
    expect(formatCurrency(100, "EUR")).toContain("€");
  });

  it("меняет запись вместе с языком", () => {
    setLanguage("en");
    setCurrency("USD");
    expect(spaces(formatCurrency(1234.56))).toBe("$1,234.56");
  });
});

describe("formatCryptoAmount", () => {
  it("не превращает дешёвую монету в ноль", () => {
    // Копеечная монета в формате с двумя знаками выглядит как «0 ₽» —
    // неотличимо от того, что она ничего не стоит.
    const formatted = formatCryptoAmount(0.000000006894);
    expect(formatted).not.toBe("0 ₽");
    expect(spaces(formatted)).toContain("6894");
  });

  it("от единицы и выше показывает обычные два знака", () => {
    expect(spaces(formatCryptoAmount(61000.5))).toBe("61 000,50 ₽");
  });

  it("ноль остаётся нулём, а не рядом нулей после запятой", () => {
    expect(spaces(formatCryptoAmount(0))).toBe("0,00 ₽");
  });
});

describe("trimTrailingZeros", () => {
  it("срезает хвост нулей, оставляя значащие знаки", () => {
    // База хранит количество как Numeric(38,18) и возвращает во всю
    // ширину: «3.000000000000000000» в поле ввода править невозможно.
    expect(trimTrailingZeros("3.000000000000000000")).toBe("3");
    expect(trimTrailingZeros("0.050000000000000000")).toBe("0.05");
  });

  it("не трогает целое без точки", () => {
    expect(trimTrailingZeros("30")).toBe("30");
    expect(trimTrailingZeros("100")).toBe("100");
  });

  it("сохраняет все значащие знаки длинного количества", () => {
    // Количество токена в восемнадцать знаков — настоящее, и округлять его
    // ради красивой записи нельзя.
    expect(trimTrailingZeros("0.000000000000000001")).toBe("0.000000000000000001");
  });

  it("из нуля в любой записи делает ноль, а не пустоту", () => {
    expect(trimTrailingZeros("0.000000")).toBe("0");
    expect(trimTrailingZeros("-0.000")).toBe("0");
  });
});

describe("formatQuantity", () => {
  it("группирует целую часть и отбрасывает лишние нули", () => {
    expect(spaces(formatQuantity("1200.00000000"))).toBe("1 200");
    expect(spaces(formatQuantity("30.50000000"))).toBe("30,5");
  });

  it("разделитель берёт у языка", () => {
    setLanguage("en");
    expect(spaces(formatQuantity("30.5"))).toBe("30.5");
  });

  it("не округляет дробную часть через число", () => {
    // Через Number() восемнадцать знаков не доживают до экрана.
    expect(formatQuantity("0.000000000000000001")).toContain("000000000000000001");
  });

  it("держит минус", () => {
    expect(spaces(formatQuantity("-1200.5"))).toBe("-1 200,5");
  });
});

describe("maskAmount", () => {
  it("скрывает сумму точками и возвращает как было", () => {
    expect(maskAmount("1 234,56 ₽", true)).toBe("••••");
    expect(maskAmount("1 234,56 ₽", false)).toBe("1 234,56 ₽");
  });
});
