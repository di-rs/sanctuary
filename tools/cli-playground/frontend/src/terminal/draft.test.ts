import { describe, expect, test } from "vite-plus/test";
import type { Terminal } from "@xterm/xterm";
import { watchDraft, type Draft } from "./draft";

function harness() {
  let osc: (data: string) => boolean = () => false;
  let parsed = () => {};
  const marker = {
    line: 0,
    isDisposed: false,
    dispose() {
      this.isDisposed = true;
    },
  };
  let lines = ["$ biggie t"];
  let wraps = [false];
  let type = "normal";
  const seen: Draft[] = [];
  const terminal = {
    parser: {
      registerOscHandler: (_: number, listener: typeof osc) => {
        osc = listener;
        return { dispose() {} };
      },
    },
    registerMarker: () => {
      marker.isDisposed = false;
      return marker;
    },
    onWriteParsed: (listener: typeof parsed) => {
      parsed = listener;
      return { dispose() {} };
    },
    buffer: {
      get active() {
        return {
          type,
          cursorX: 2,
          getLine(row: number) {
            return lines[row] === undefined
              ? undefined
              : {
                  isWrapped: wraps[row],
                  translateToString(trim: boolean, start: number) {
                    const text = lines[row].slice(start);
                    return trim ? text.trimEnd() : text;
                  },
                };
          },
        };
      },
    },
  } as unknown as Terminal;
  const watcher = watchDraft(terminal, (value) => seen.push(value));
  return {
    watcher,
    seen,
    prompt() {
      osc("B");
      parsed();
    },
    update(value: string[], wrapped = value.map(() => false)) {
      lines = value;
      wraps = wrapped;
      parsed();
    },
    program() {
      osc("C");
      parsed();
    },
    alternate() {
      type = "alternate";
      parsed();
    },
  };
}
describe("echoed Bash draft", () => {
  test("tracks history and edits from echoed text rather than keystrokes", () => {
    const h = harness();
    h.prompt();
    expect(h.seen.at(-1)).toEqual({ text: "biggie t", ready: true });
    h.update(["$ echor hello"]);
    expect(h.seen.at(-1)?.text).toBe("echor hello");
    h.update(["$ biggie "]);
    expect(h.seen.at(-1)?.text).toBe("biggie");
  });
  test("joins wrapped input but excludes subsequent output lines", () => {
    const h = harness();
    h.prompt();
    h.update(["$ biggie text ", "--lines 5", "other output"], [false, true, false]);
    expect(h.seen.at(-1)?.text).toBe("biggie text --lines 5");
  });
  test("stops suggestions for submitted input, running programs and alternate buffers", () => {
    const h = harness();
    h.prompt();
    h.watcher.invalidate();
    expect(h.seen.at(-1)?.ready).toBe(false);
    h.prompt();
    h.program();
    expect(h.seen.at(-1)?.ready).toBe(false);
    h.prompt();
    h.alternate();
    expect(h.seen.at(-1)?.ready).toBe(false);
    h.watcher.dispose();
  });
});
