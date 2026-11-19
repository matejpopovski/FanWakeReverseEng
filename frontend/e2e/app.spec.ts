import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Password").fill("e2e-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("mode-badge")).toContainText("MOCK MODE");
}

test.describe.configure({ mode: "serial" });

test("rejects a wrong password", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Password").fill("nope");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Wrong password");
});

test("overview shows synced mock fans", async ({ page }) => {
  await login(page);
  await expect(page.getByTestId("kpi-fans")).toContainText("30");
});

test("fan message -> AI draft -> edit -> approve -> sent", async ({ page }) => {
  await login(page);
  await page.goto("/autopilot");
  await page.getByTestId("autopilot-toggle").click();
  await page.getByTestId("save").click();
  await expect(page.getByTestId("save")).toHaveText("Saved");

  await page.goto("/inbox");
  await page.getByTestId("simulate-input").fill("hey, how was your weekend?");
  await page.getByTestId("simulate").click();
  await expect(page.getByTestId("thread")).toContainText("how was your weekend?");

  await page.goto("/review");
  const card = page.getByTestId("draft-card").first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.getByTestId("edit").click();
  await card.getByLabel("Message 1").fill("it was lovely, thanks for asking! yours?");
  await card.getByTestId("approve").click();
  await expect(page.getByTestId("recent-sent")).toContainText("it was lovely", { timeout: 20_000 });
});

test("sincere AI question escalates and stops automation", async ({ page }) => {
  await login(page);
  await page.goto("/inbox");
  await page.getByTestId("simulate-input").fill("wait, are you a bot?");
  await page.getByTestId("simulate").click();
  await page.goto("/review");
  await expect(page.getByTestId("escalation").first()).toContainText("AI or a real person");
});

test("kill switch pauses and resumes", async ({ page }) => {
  await login(page);
  await page.getByTestId("kill-switch").click();
  await expect(page.getByText("ALL AUTOMATION PAUSED")).toBeVisible();
  await page.getByTestId("kill-switch").click();
  await expect(page.getByText("ALL AUTOMATION PAUSED")).toHaveCount(0);
});

test("PPV template validation and creation", async ({ page }) => {
  await login(page);
  await page.goto("/ppv");
  await expect(page.getByTestId("template-card")).toHaveCount(6);
  const before = 6;
  await page.getByTestId("add-template").click();
  await page.getByLabel("Template name").fill("E2E set");
  await page.getByLabel("Description for AI").fill("Test content for e2e");
  await page.locator("img").first().click();
  await page.getByLabel("Price ($)").fill("2");
  await page.getByTestId("save-template").click();
  await expect(page.getByRole("alert")).toContainText("$3.00");
  await page.getByLabel("Price ($)").fill("5");
  await page.getByTestId("save-template").click();
  await expect(page.getByTestId("template-card")).toHaveCount(before + 1);
});

test("fan memory edit persists", async ({ page }) => {
  await login(page);
  await page.goto("/fans");
  await page.getByTestId("fan-table").locator("tr").first().click();
  const drawer = page.getByTestId("fan-drawer");
  await drawer.getByRole("button", { name: "Engine" }).click();
  await drawer.getByTestId("memory").fill("[ABOUT]\nloves e2e tests");
  await drawer.getByRole("button", { name: "Save memory" }).click();
  await page.reload();
  await page.getByTestId("fan-drawer").getByRole("button", { name: "Engine" }).click();
  await expect(page.getByTestId("memory")).toHaveValue(/loves e2e tests/);
});
