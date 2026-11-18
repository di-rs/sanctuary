import type { RunnableEnvironment } from "../services/environment";
import type { BrowserTerminal } from "./browser";
import type { Draft } from "./draft";
import type { SessionState } from "./session";

export class WorkspaceTerminal {
  session = $state.raw<SessionState>({
    phase: "connecting",
    label: "Connecting",
    message: null,
    canReconnect: false,
  });
  draft = $state.raw<Draft>({ text: "", ready: false });
  connected = $derived(this.session.phase === "connected");
  #browser?: BrowserTerminal;

  attach(host: HTMLDivElement, environment: RunnableEnvironment, onError: () => void) {
    let mounted = true;
    void import("./browser")
      .then(({ createBrowserTerminal }) => {
        if (!mounted) return;
        this.#browser = createBrowserTerminal(
          host,
          environment.id,
          environment.revision,
          (session) => (this.session = session),
          (draft) => (this.draft = draft),
        );
        this.#browser.startFresh();
      })
      .catch(() => {
        if (mounted) onError();
      });
    return () => {
      mounted = false;
      this.#browser?.dispose();
      this.#browser = undefined;
    };
  }

  replaceLine(value: string) {
    if (this.connected && this.draft.ready) this.#browser?.replaceLine(value);
  }

  disconnect() {
    this.#browser?.disconnect();
  }

  reconnect() {
    this.#browser?.resumeExisting();
  }
}
