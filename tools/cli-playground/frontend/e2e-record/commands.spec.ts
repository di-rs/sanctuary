import { expect, test } from "@playwright/test";
import { Buffer } from "node:buffer";

// cli-record validates the selected TOML cases before starting the stack.
interface Demo {
  args: string[];
  setup?: string;
  stdin?: string;
  ready?: string;
  keys: string[];
  after?: string;
}
const { cli, cases } = JSON.parse(process.env.CLI_RECORD_PLAN ?? "{}") as {
  cli: string;
  cases: Demo[];
};
if (!cli || !cases?.length) throw new Error("Select demos with cli-record");

function quote(token: string): string {
  return /^[\w./:@%+=,-]+$/.test(token) ? token : "'" + token.replaceAll("'", "'\\''") + "'";
}

test(cli, async ({ page }) => {
  let output = "";
  page.on("websocket", (socket) => {
    socket.on("framereceived", ({ payload }) => {
      // PTY frames carry an eight-byte sequence number before the terminal bytes.
      if (Buffer.isBuffer(payload)) output += payload.subarray(8).toString("latin1");
    });
  });
  await page.goto("/");
  await expect(page.locator("#connection-status")).toHaveText("Connected", { timeout: 30_000 });
  const input = page.locator(".xterm-helper-textarea");
  const prompt = "\x1b]133;B\x07";
  const executing = "\x1b]133;C\x07";
  await expect.poll(() => output).toContain(prompt);
  function duringCommand() {
    const start = output.indexOf(executing);
    return start < 0 ? "" : output.slice(start + executing.length);
  }

  async function run(line: string, ready?: string, keys: string[] = []) {
    await input.focus();
    await input.evaluate((element, text) => {
      const clipboardData = new DataTransfer();
      clipboardData.setData("text/plain", text);
      element.dispatchEvent(new ClipboardEvent("paste", { bubbles: true, clipboardData }));
    }, line);
    // Leave the command visible long enough to read before executing it.
    await page.waitForTimeout(900);
    output = "";
    await input.press("Enter");
    if (ready) {
      await expect
        .poll(duringCommand, { timeout: 60_000 })
        .toContain(Buffer.from(ready).toString("latin1"));
      for (const key of keys) await input.press(key);
    }
    // Both success and error output belong in a demo. Wait for Bash to accept input again.
    await expect.poll(duringCommand, { timeout: 60_000 }).toContain(prompt);
    await page.waitForTimeout(1800);
  }

  for (const demo of cases) {
    if (demo.setup) await run(demo.setup);
    const command = [cli, ...demo.args].map(quote).join(" ");
    await run(
      demo.stdin === undefined ? command : `printf %s ${quote(demo.stdin)} | ${command}`,
      demo.ready,
      demo.keys,
    );
    if (demo.after) await run(demo.after);
  }
});
