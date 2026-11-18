<script lang="ts">
  import { createFocusTrap } from "focus-trap";
  import { tick } from "svelte";
  import { MediaQuery } from "svelte/reactivity";
  import Explorer from "../explorer/Explorer.svelte";
  import type { RunnableEnvironment } from "../services/environment";
  import TerminalPanel from "../terminal/TerminalPanel.svelte";
  import { WorkspaceTerminal } from "../terminal/workspace-terminal.svelte";
  import Button from "../ui/Button.svelte";

  let { environment, restart, onTerminalError }: {
    environment: RunnableEnvironment;
    restart: () => void;
    onTerminalError: () => void;
  } = $props();
  const terminal = new WorkspaceTerminal();
  const mobile = new MediaQuery("(width < 800px)");
  let drawerOpen = $state(false);

  function trapDrawer(node: HTMLElement) {
    if (!mobile.current || !drawerOpen) return;
    const trap = createFocusTrap(node, {
      initialFocus: node,
      fallbackFocus: node,
      isolateSubtrees: true,
      delayReturnFocus: false,
      setReturnFocus: () =>
        mobile.current ? document.getElementById("explorer-button") ?? false : node,
      onDeactivate() {
        drawerOpen = false;
      },
    }).activate();
    return () => trap.deactivate();
  }
  async function replaceLine(value: string) {
    if (!terminal.connected || !terminal.draft.ready) return;
    drawerOpen = false;
    await tick();
    terminal.replaceLine(value);
  }
</script>

<div class="relative flex min-h-0 flex-1 desktop:grid desktop:grid-cols-[360px_minmax(0,1fr)]">
  <div
    id="explorer"
    role={mobile.current ? "dialog" : "complementary"}
    aria-label="Command explorer"
    aria-modal={mobile.current && drawerOpen ? true : undefined}
    tabindex="-1"
    inert={mobile.current && !drawerOpen}
    class="fixed inset-x-0 top-12 bottom-0 z-30 min-h-0 outline-none inert:pointer-events-none desktop:static"
    {@attach trapDrawer}
  >
    {#if mobile.current && drawerOpen}
      <button type="button" tabindex="-1" class="absolute inset-0 bg-black/60"
        aria-label="Close command explorer" onclick={() => drawerOpen = false}></button>
    {/if}
    <div class={["relative flex h-full w-[min(360px,92vw)] flex-col border-r border-line bg-panel motion-safe:transition-transform motion-safe:duration-120 desktop:w-auto desktop:translate-x-0",
      !drawerOpen && "-translate-x-full"]}>
      {#if mobile.current}
        <button type="button" class="shrink-0 border-b border-line px-4.5 py-3 text-right text-[10px] text-detail"
          aria-label="Close explorer ×" onclick={() => drawerOpen = false}>Close explorer <span class="ml-2" aria-hidden="true">×</span></button>
      {/if}
      <Explorer {environment} connected={terminal.connected} draft={terminal.draft} {replaceLine} />
    </div>
  </div>
  <TerminalPanel {environment} {terminal} {onTerminalError} {restart}>
    <Button id="explorer-button" variant="toolbar" class="border border-neutral-700 px-2 desktop:hidden"
      aria-label="Explore" aria-controls="explorer" aria-expanded={drawerOpen}
      onclick={() => drawerOpen = true}>Explore</Button>
  </TerminalPanel>
</div>
