import type { Terminal, IMarker } from "@xterm/xterm";

export interface Draft {
  text: string;
  ready: boolean;
}
// The sandbox emits prompt boundaries. Read the echoed Readline buffer, not a
// second keystroke model: history, completion, cursor edits and paste stay aligned.
export function watchDraft(terminal: Terminal, changed: (draft: Draft) => void) {
  let marker: IMarker | undefined;
  let column = 0;
  let active = false;
  const publish = () => {
    const buffer = terminal.buffer.active;
    if (!active || !marker || marker.isDisposed || buffer.type !== "normal") {
      changed({ text: "", ready: false });
      return;
    }
    let end = marker.line;
    while (buffer.getLine(end + 1)?.isWrapped) end++;
    if (end - marker.line > 32) {
      changed({ text: "", ready: false });
      return;
    }
    let text = "";
    for (let row = marker.line; row <= end; row++)
      text +=
        buffer.getLine(row)?.translateToString(row === end, row === marker.line ? column : 0) ?? "";
    changed({ text, ready: true });
  };
  const boundaries = terminal.parser.registerOscHandler(133, (data) => {
    if (data === "B") {
      marker?.dispose();
      marker = terminal.registerMarker(0);
      column = terminal.buffer.active.cursorX;
      active = true;
    } else if (data === "A" || data === "C") active = false;
    return false;
  });
  const parsed = terminal.onWriteParsed(publish);
  return {
    invalidate() {
      active = false;
      publish();
    },
    dispose() {
      boundaries.dispose();
      parsed.dispose();
      marker?.dispose();
    },
  };
}
