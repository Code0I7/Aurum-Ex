import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** Thin wrapper over the real HTTP API (proxied at /api by nginx, same as
 * the frontend uses) — fast, reliable fixture setup so each spec can drive
 * the actual UI against known data instead of guessing at pre-existing
 * account/category IDs. */

export async function getDefaultAccountId(request: APIRequestContext): Promise<number> {
  const resp = await request.get("/api/accounts");
  const accounts = await resp.json();
  return accounts[0].id;
}

export async function getCategoryId(request: APIRequestContext, name: string): Promise<number> {
  const resp = await request.get("/api/categories");
  const categories = await resp.json();
  const match = categories.find((c: { name: string }) => c.name === name);
  if (!match) throw new Error(`category "${name}" not found`);
  return match.id;
}

export interface TransactionInput {
  account_id: number;
  category_id?: number;
  type: "income" | "expense" | "transfer";
  amount: string;
  description: string;
  date: string; // YYYY-MM-DD
}

export async function createTransaction(request: APIRequestContext, input: TransactionInput): Promise<void> {
  const resp = await request.post("/api/transactions", { data: input });
  if (!resp.ok()) {
    throw new Error(`failed to create transaction: ${resp.status()} ${await resp.text()}`);
  }
}


/**
 * Открыть дашборд на конкретном месяце.
 *
 * Три шага, а не два, и порядок обязателен: дашборд открывается на годе, а
 * кнопок месяцев в этом режиме нет вовсе — значит сначала «Месяц», и только
 * потом год и сам месяц.
 *
 * Раньше спеки щёлкали год и месяц сразу, потому что месяцы на дашборде
 * были видны всегда. Период по умолчанию сменился на год, и все пять спек
 * упали на ожидании кнопки «Авг». Вынесено сюда, чтобы следующая такая
 * правка интерфейса меняла одно место, а не пять.
 */
export async function openDashboardMonth(page: Page, year: string, month: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "Месяц", exact: true }).click();
  await page.getByRole("button", { name: /^\d{4}$/ }).first().click();
  await page.getByRole("option", { name: year }).click();
  const pill = page.getByRole("button", { name: month, exact: true });
  await expect(pill).toBeVisible();
  await pill.click();
}
