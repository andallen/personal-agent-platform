import { test, expect } from "@playwright/test";

test("page loads and shows top bar", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByLabel("project")).toBeVisible();
  await expect(page.getByLabel("model")).toBeVisible();
});

test("opening model sheet shows options", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("model").click();
  await expect(page.getByText(/Opus|Sonnet|Haiku/i).first()).toBeVisible();
});

test("typing slash opens picker", async ({ page }) => {
  await page.goto("/");
  const ta = page.getByLabel("message");
  await ta.fill("/cl");
  await page.waitForTimeout(200);
  await expect(page.locator("text=/clear/").first()).toBeVisible();
});
