import { expect, type Page } from "@playwright/test";

export async function openExplorer(page: Page) {
  const toggle = page.getByRole("button", { name: "Explore", exact: true });
  if ((await toggle.isVisible()) && (await toggle.getAttribute("aria-expanded")) === "false") {
    await toggle.click();
  }
  await expect(page.getByText("Command builder", { exact: true })).toBeVisible();
}
export async function openSampleFiles(page: Page) {
  await openExplorer(page);
  const summary = page.getByText("Sample files", { exact: true });
  if (!(await summary.evaluate((node) => node.closest("details")?.open))) {
    await summary.click();
  }
}
