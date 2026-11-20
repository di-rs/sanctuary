// Keep the actual browser clients open while pytest updates and removes a neighboring PR app.
import { createInterface } from "node:readline";
import { chromium, expect } from "@playwright/test";

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const terminals = [];
  for (const url of process.argv.slice(2)) {
    const page = await context.newPage();
    const connection = page.waitForEvent("websocket");
    await page.goto(url);
    await expect(page.locator("#connection-status")).toHaveText("Connected", { timeout: 45_000 });
    terminals.push({ page, connection: await connection });
  }

  for await (const milestone of createInterface({ input: process.stdin })) {
    for (const { page, connection } of terminals) {
      await page.locator(".xterm-helper-textarea").pressSequentially(`echor '${milestone}-'"ok"\n`);
      await expect(page.locator(".xterm-rows")).toContainText(`${milestone}-ok`);
      expect(connection.isClosed()).toBe(false);
    }
    process.stdout.write(milestone + "\n");
  }
} finally {
  await browser.close();
}
