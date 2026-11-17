import { expect, test } from "@playwright/test";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { z } from "zod";
import { parseCatalog } from "../src/catalog";
import { exercises, recipe } from "./exercises";

const packages = z
  .record(z.string(), z.string())
  .parse(JSON.parse(process.env.CLI_RECORD_PACKAGES ?? "{}"));
if (!Object.keys(packages).length) throw new Error("Use local-dev record to select CLIs");

function quote(token: string): string {
  return /^[\w./:@%+=,-]+$/.test(token) ? token : "'" + token.replaceAll("'", "'\\''") + "'";
}

for (const [name, file] of Object.entries(packages)) {
  test(name, async ({ page, request }) => {
    const plan = recipe.parse(JSON.parse(readFileSync(file, "utf8")));
    let frames: Buffer[] = [];
    page.on("websocket", (socket) => {
      socket.on("framereceived", ({ payload }) => {
        // Only PTY output is binary. The first eight bytes carry its sequence number.
        if (Buffer.isBuffer(payload)) frames.push(payload.subarray(8));
      });
    });
    await page.goto("/");
    await expect(page.locator("#connection-status")).toHaveText("Connected", { timeout: 30_000 });
    const id = new URL(page.url()).pathname.split("/").at(-1);
    const metadata = await (await request.get(`/api/environments/${id}`)).json();
    const response = await request.get(
      `/api/environments/${id}/revisions/${metadata.revision}/catalog`,
    );
    expect(response.ok()).toBeTruthy();
    const catalog = parseCatalog(
      await response.json(),
      metadata.revision.split("-")[0],
      metadata.clis,
    );
    const cli = catalog.clis.find((entry) => entry.name === name);
    if (!cli) throw new Error(`${name} is missing from the running playground`);
    const steps = exercises(cli.head.command, plan.cases);
    const input = page.locator(".xterm-helper-textarea");
    await expect(page.locator(".xterm-accessibility-tree")).toContainText("dev ~ $");
    const output = () => Buffer.concat(frames).toString();
    async function enter(line: string) {
      await input.focus();
      await input.evaluate((element, text) => {
        const clipboardData = new DataTransfer();
        clipboardData.setData("text/plain", text);
        element.dispatchEvent(new ClipboardEvent("paste", { bubbles: true, clipboardData }));
      }, line);
      await input.press("Enter");
    }
    // Let Bash report each exit status after execution. The video shows the same
    // commands a user would type, including interactive programs in the foreground.
    await enter(`n=0; PROMPT_COMMAND='s=$?; printf "\\n[run %d exit %d]\\n" "$((++n))" "$s"'`);
    await expect.poll(output).toContain("[run 1 exit 0]");
    let sequence = 1;
    async function run(line: string, status: number, ready?: string, keys?: string[]) {
      frames = [];
      sequence++;
      await enter(line);
      if (ready) await expect.poll(output).toContain(ready);
      for (const key of keys ?? []) await input.press(key);
      const marker = new RegExp(`\\[run ${sequence} exit (\\d+)\\]`);
      await expect.poll(() => output().match(marker)?.[1], { message: line }).toBe(String(status));
      // Bash emits OSC 133;C after echoing the command and before executing it.
      const boundary = "\x1b]133;C\x07";
      const received = output();
      expect(received).toContain(boundary);
      return received.slice(received.indexOf(boundary) + boundary.length).split(marker)[0]!;
    }
    if (plan.setup) await run(plan.setup, 0);
    for (const step of steps) {
      const command = [name, ...step.args].map(quote).join(" ");
      const line =
        step.stdin === undefined ? command : `printf %s ${quote(step.stdin)} | ${command}`;
      const printed = await run(line, step.exit, step.ready, step.keys);
      if (step.contains !== undefined) expect(printed, command).toContain(step.contains);
      if (step.check) await run(step.check, 0);
      // Reading time in the exported video, after the assertions have completed.
      await page.waitForTimeout(750);
    }
  });
}
