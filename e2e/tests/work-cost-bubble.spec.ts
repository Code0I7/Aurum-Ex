import { test, expect } from "@playwright/test";
import { createTransaction, getCategoryId, getDefaultAccountId, openDashboardMonth } from "./helpers";

/**
 * Пузырь с точным числом часов над ценой покупки в рабочих днях.
 *
 * Раньше часы показывались системной подсказкой (`title`), и она рисуется у
 * курсора — курсор же и перекрывал именно то число, за которым к ней
 * потянулись. Проверить это может только браузер: ни тип, ни модульный тест
 * не знают, где на экране окажется стрелка.
 *
 * Поэтому проверка здесь не «пузырь появился», а «пузырь выше числа». Если
 * кто-нибудь поставит его снизу или вернёт `title`, тест упадёт.
 *
 * Данные свои, в 2019 году: спеки делят один стенд, и у каждой свой месяц,
 * чтобы числа не сходились в одном периоде.
 */
test("часы показываются пузырём над ценой в днях, а не под курсором", async ({ page, request }) => {
  const accountId = await getDefaultAccountId(request);
  const salaryId = await getCategoryId(request, "Salary");
  const groceriesId = await getCategoryId(request, "Groceries");

  // Смена 10,5 часа: 210 часов на 20 рабочих дней. Именно из этих двух чисел
  // приложение и берёт длину дня — восьмичасовой день здесь был бы чужой
  // меркой и дал бы 2,6 дня вместо двух.
  const work = await request.put("/api/work-periods", {
    data: { year: 2019, month: 5, hours: "210.00", workdays: 20 },
  });
  expect(work.ok()).toBeTruthy();

  // 210 000 ₽ за 210 часов — ровно 1000 ₽ в час, чтобы числа читались глазом.
  await createTransaction(request, {
    account_id: accountId,
    category_id: salaryId,
    type: "income",
    amount: "210000.00",
    description: "2019 may salary",
    date: "2019-05-15",
  });
  // 21 000 ₽ — это 21 час, то есть ровно два рабочих дня по 10,5.
  await createTransaction(request, {
    account_id: accountId,
    category_id: groceriesId,
    type: "expense",
    amount: "21000.00",
    description: "2019-may-bubble-check",
    date: "2019-05-20",
  });

  await openDashboardMonth(page, "2019", "Май");

  const card = page.locator("div.rounded-xl", {
    has: page.getByText("Самые крупные траты", { exact: true }),
  });
  const cost = card.getByText("раб. дн.", { exact: false }).first();
  await expect(cost).toBeVisible();
  // Длина дня взята из данных, а не восьмёрка: 21 час при смене 10,5 — это
  // два дня. По восьмичасовому дню вышло бы 2,6.
  await expect(cost).toContainText("2,0");

  const bubble = page.getByRole("tooltip");
  await expect(bubble).toHaveCount(0); // до наведения пузыря нет

  await cost.hover();
  await expect(bubble).toBeVisible();
  // Точное число за округлённым: двадцать один час.
  await expect(bubble).toContainText("21,0");

  const bubbleBox = (await bubble.boundingBox())!;
  const costBox = (await cost.boundingBox())!;
  const amountBox = (await card.getByText("21 000,00", { exact: false }).first().boundingBox())!;

  // Середины совпадают — и сравниваются именно строки текста, а не коробки
  // элементов. Коробки совпадали и тогда, когда пузырь стоял на две с
  // половиной точки выше: буквы садятся в строку по метрикам шрифта, и при
  // разном межстрочном интервале два отцентрованных по коробкам текста
  // расходятся. Видно это глазом, а замером коробок — нет.
  const lines = await cost.evaluate((el) => {
    function lineCenter(node: Element | null) {
      if (!node) return null;
      const range = document.createRange();
      range.selectNodeContents(node);
      const rect = range.getBoundingClientRect();
      return rect.top + rect.height / 2;
    }
    return { number: lineCenter(el), bubble: lineCenter(document.querySelector('[role="tooltip"]')) };
  });
  expect(lines.bubble).not.toBeNull();
  expect(Math.abs(lines.bubble! - lines.number!)).toBeLessThanOrEqual(1);

  // Пузырь целиком левее числа: курсор стоит на числе и его не закрывает.
  expect(bubbleBox.x + bubbleBox.width).toBeLessThanOrEqual(costBox.x);
  // И не налезает на саму сумму — первая попытка ставила его сверху, где он
  // закрывал ровно то число, с которым его и сравнивают.
  const overlapsAmount =
    bubbleBox.x < amountBox.x + amountBox.width &&
    bubbleBox.x + bubbleBox.width > amountBox.x &&
    bubbleBox.y < amountBox.y + amountBox.height &&
    bubbleBox.y + bubbleBox.height > amountBox.y;
  expect(overlapsAmount).toBe(false);

  // И уходит, когда курсор ушёл.
  await page.getByText("Самые крупные траты", { exact: true }).hover();
  await expect(bubble).toHaveCount(0);
});
