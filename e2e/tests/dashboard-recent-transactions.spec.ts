import { test, expect } from "@playwright/test";
import { createTransaction, getCategoryId, getDefaultAccountId, openDashboardMonth } from "./helpers";

// Regression for the Aug 2026 bug: RecentTransactionsCard queried
// transactions without year/month at all, so switching the Dashboard's
// month did nothing — it just showed the latest N transactions globally,
// including ones from a completely different month. See UPDATES.md
// (v0.15.3) and frontend/src/components/dashboard/RecentTransactionsCard.tsx.
test("Recent Transactions on Dashboard only shows the selected month", async ({ page, request }) => {
  const accountId = await getDefaultAccountId(request);
  const categoryId = await getCategoryId(request, "Groceries");

  await createTransaction(request, {
    account_id: accountId,
    category_id: categoryId,
    type: "expense",
    amount: "12.00",
    description: "july-2015-only-txn",
    date: "2015-07-26",
  });
  await createTransaction(request, {
    account_id: accountId,
    category_id: categoryId,
    type: "expense",
    amount: "34.00",
    description: "august-2015-only-txn",
    date: "2015-08-08",
  });

  await openDashboardMonth(page, "2015", "Авг");

  const recentCard = page.locator("div.rounded-xl", { has: page.getByText("Последние транзакции", { exact: true }) });
  await expect(recentCard.getByText("august-2015-only-txn")).toBeVisible();
  await expect(recentCard.getByText("july-2015-only-txn")).toHaveCount(0);
});
