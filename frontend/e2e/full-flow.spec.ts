import { test, expect, type Page } from "@playwright/test";
import path from "path";

const OWNER_ID = "0.0.9160905";
const SUPPLIER_ID = "0.0.9160906";
const JOB_TITLE = "Deep clean before guest arrival";

async function loginAs(page: Page, userType: "owner" | "supplier") {
  const accountId = userType === "owner" ? OWNER_ID : SUPPLIER_ID;

  await page.locator(".dev-toggle input[type=checkbox]").check();
  await page.locator(".segmented").locator("button", { hasText: userType === "owner" ? "Owner" : "Supplier" }).click();
  await page.locator(`input[value="${accountId}"]`).waitFor({ state: "attached", timeout: 5_000 });
  await page.locator("button.primary-button", { hasText: "Connect persona" }).click();

  await expect(page.locator(".topbar")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".dev-badge")).toHaveText("DEV");
}

async function signOut(page: Page) {
  await page.locator("button.ghost-button", { hasText: "Sign out" }).click();
  await expect(page.locator(".login-screen")).toBeVisible();
}

// Open the job created by this run from the jobs list, into either the job or bid workspace.
async function openJob(page: Page, view: "job" | "bids") {
  await page.locator(".role-nav button", { hasText: "Jobs" }).click();
  const row = page.locator(".job-row", { hasText: JOB_TITLE }).first();
  await expect(row).toBeVisible({ timeout: 10_000 });
  if (view === "bids") {
    await row.getByRole("button", { name: "Bids" }).click();
  } else {
    await row.locator(".job-row-main").click();
  }
}

test.describe("EscrowEye full flow", () => {
  test("owner creates home and job, supplier bids, owner funds, supplier uploads, owner confirms", async ({ page }) => {
    // ── 1. Owner login ──
    await test.step("Owner login", async () => {
      await page.goto("/");
      await expect(page.locator(".login-screen")).toBeVisible();

      await loginAs(page, "owner");

      await expect(page.locator(".role-nav")).toBeVisible();
      await expect(page.locator(".role.role-owner")).toHaveText("owner");
      await expect(page.locator(".role-nav button.active")).toHaveText("Jobs");
    });

    // ── 2. Create home ──
    let homeName = "";
    await test.step("Owner creates home", async () => {
      await page.locator(".role-nav button", { hasText: "Create home" }).click();
      await expect(page.locator("h1", { hasText: "Create home" })).toBeVisible();

      homeName = `E2E Home ${Date.now()}`;
      await page.getByLabel("Home name").fill(homeName);
      await page.getByLabel("Address").fill("123 E2E Test Lane");
      await page.locator("button.primary-button", { hasText: "Save home" }).click();

      await expect(page.locator(".mini-card", { hasText: homeName })).toBeVisible({ timeout: 10_000 });

      await page.locator("input[placeholder='Room']").fill("Living Room");
      await page.locator("input[placeholder='m2']").fill("30");
      await page.locator("button.secondary-button", { hasText: "Add room" }).click();
    });

    // ── 3. Create job ──
    await test.step("Owner creates job (auto-pays x402)", async () => {
      await page.locator(".role-nav button", { hasText: "Create job" }).click();
      await expect(page.locator("h1", { hasText: "Create job" })).toBeVisible();

      await page.locator("input[placeholder='Job title']").fill(JOB_TITLE);
      await page.locator("textarea[placeholder='Scope']").fill("Clean all listed rooms, surfaces, floors, and bathrooms.");
      await page.locator("input[placeholder='Suggested HBAR']").fill("50");
      await page.locator("textarea[placeholder='Access notes']").fill("Gate code 1234, key under mat.");
      await page.locator("input[placeholder='Available times']").fill("Weekdays after 2pm");

      await page.locator("button.primary-button", { hasText: "Post job" }).click();

      await expect(page.locator(".notice")).toContainText(/Job #\d+ created/, { timeout: 15_000 });
    });

    // ── 4. Switch to supplier, place bid ──
    await test.step("Supplier login and place bid", async () => {
      await signOut(page);
      await loginAs(page, "supplier");

      await openJob(page, "bids");
      await expect(page.locator("h2", { hasText: /Job #/ })).toBeVisible();

      await page.locator("input[placeholder='HBAR']").fill("42");
      await page.locator("input[placeholder='Bid message']").fill("E2E test bid");
      await page.locator("button.primary-button", { hasText: "Place bid" }).click();

      await expect(page.locator(".bid-card").first()).toBeVisible({ timeout: 10_000 });
    });

    // ── 5. Switch to owner, award bid ──
    await test.step("Owner awards bid", async () => {
      await signOut(page);
      await loginAs(page, "owner");

      await openJob(page, "bids");

      const chooseButton = page.locator("button.secondary-button", { hasText: "Choose bid" }).first();
      await expect(chooseButton).toBeVisible({ timeout: 10_000 });
      await chooseButton.click();

      await expect(page.locator(".notice")).toContainText("Bid awarded.", { timeout: 10_000 });
    });

    // ── 6. Fund escrow ──
    await test.step("Owner funds escrow (dev mode auto-sign)", async () => {
      await page.locator("button.ghost-button", { hasText: "Job view" }).click();
      await expect(page.locator(".context-head h1")).toContainText(/Deep clean/, { timeout: 10_000 });

      await page.locator("button.secondary-button", { hasText: "Fund escrow" }).click();
      await expect(page.locator(".notice")).toContainText("Escrow funded.", { timeout: 15_000 });
    });

    // ── 7. Switch to supplier, upload photo, mark ready ──
    await test.step("Supplier uploads photo and marks ready", async () => {
      await signOut(page);
      await loginAs(page, "supplier");

      await openJob(page, "job");
      await expect(page.locator(".context-head h1")).toContainText(/Deep clean/, { timeout: 10_000 });

      await page.locator("input[type=file]").setInputFiles([
        path.resolve("e2e/clean-room.jpg"),
        path.resolve("e2e/messy-room.jpg"),
      ]);
      await page.locator("button.secondary-button", { hasText: "Upload photos" }).click();
      await expect(page.locator(".notice")).toContainText("Photos uploaded.", { timeout: 10_000 });

      await page.locator("button.primary-button", { hasText: "Mark ready" }).click();
      await expect(page.locator(".notice")).toContainText("Job marked ready.", { timeout: 10_000 });
    });

    // ── 8. Switch to owner, confirm ──
    await test.step("Owner confirms job completion", async () => {
      await signOut(page);
      await loginAs(page, "owner");

      await openJob(page, "job");
      await expect(page.locator(".context-head h1")).toContainText(/Deep clean/, { timeout: 10_000 });

      await page.locator("button.primary-button", { hasText: "Confirm" }).click();
      await expect(page.locator(".notice")).toContainText("Job confirmed.", { timeout: 15_000 });
    });
  });
});
