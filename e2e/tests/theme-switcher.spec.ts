import { test, expect, type Page } from "@playwright/test";

// The theme picker (Settings → Тема оформления): light/dark/system, with
// system meant to follow the OS live and light/dark meant to override it.
// See frontend/src/lib/theme.ts and index.html's anti-FOUC inline script.

/** Разложенная тема: «light» или «dark», что бы ни стояло в выборе.
 *  Проверять по ней, а не по цвету: цвет — вопрос оформления, а их три. */
async function scheme(page: Page): Promise<string | null> {
  return page.evaluate(() => document.documentElement.getAttribute("data-scheme"));
}

/** Выбор человека: «light», «dark» или ничего, если выбрана системная. */
async function forcedTheme(page: Page): Promise<string | null> {
  return page.evaluate(() => document.documentElement.getAttribute("data-theme"));
}

async function surface0(page: Page): Promise<string> {
  return page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--surface-0").trim());
}

test.describe("theme picker", () => {
  test.use({ colorScheme: "dark" }); // simulates the OS being in dark mode

  test("an explicit choice overrides the OS theme, and persists across reload", async ({ page }) => {
    await page.goto("/settings");

    // Отсчёт ведётся от того, что получилось, а не от кода цвета. Раньше
    // здесь стояло «#0d0d0d», и тест упал, когда полотно тёмного
    // оформления перекрасили в «#08080a»: проверялась палитра, а проверять
    // надо было, что выбор человека сильнее системного.
    expect(await scheme(page)).toBe("dark"); // «системная» следует за тёмной ОС
    expect(await forcedTheme(page)).toBeNull();
    const osDarkSurface = await surface0(page);

    await page.getByRole("button", { name: "Светлая", exact: true }).click();
    expect(await scheme(page)).toBe("light"); // светлая вопреки тёмной ОС
    expect(await forcedTheme(page)).toBe("light");
    const forcedLightSurface = await surface0(page);
    expect(forcedLightSurface).not.toBe(osDarkSurface);

    await page.reload();
    // Переживает перезагрузку, а не живёт только в памяти страницы.
    expect(await scheme(page)).toBe("light");
    expect(await surface0(page)).toBe(forcedLightSurface);

    await page.getByRole("button", { name: "Системная", exact: true }).click();
    expect(await scheme(page)).toBe("dark"); // снова за ОС, а она всё ещё тёмная
    expect(await surface0(page)).toBe(osDarkSurface);
  });

  test("switching back to system never leaves a stale forced theme behind", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("button", { name: "Тёмная", exact: true }).click();
    await page.getByRole("button", { name: "Системная", exact: true }).click();
    expect(await forcedTheme(page)).toBeNull();
  });
});
