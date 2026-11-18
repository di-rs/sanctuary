<script lang="ts">
  import type { Snippet } from "svelte";
  import type { RunnableEnvironment } from "../services/environment";
  import Banner from "../ui/Banner.svelte";
  import Button from "../ui/Button.svelte";
  import TerminalStatus from "./TerminalStatus.svelte";
  import type { WorkspaceTerminal } from "./workspace-terminal.svelte";

  let { environment, terminal, onTerminalError, restart, children }: {
    environment: RunnableEnvironment;
    terminal: WorkspaceTerminal;
    onTerminalError: () => void;
    restart: () => void;
    children: Snippet;
  } = $props();
  const session = $derived(terminal.session);

</script>

<section class="flex min-h-60 min-w-0 flex-1 flex-col bg-paper desktop:min-h-0" aria-labelledby="terminal-heading">
  <div class="flex min-h-11 items-center justify-between gap-2 border-b border-line px-3 desktop:gap-3 desktop:px-4.5 wide:px-6">
    <div class="flex min-w-0 items-center gap-2.5 desktop:gap-3.5">
      {@render children()}
      <h1 id="terminal-heading" class="text-[11px]">Terminal</h1>
      <span class="hidden font-mono text-[10px] text-muted desktop:inline">bash</span>
    </div>
    <div class="flex items-center gap-2.5 desktop:gap-4">
      <Button id="disconnect-button" variant="toolbar" disabled={!terminal.connected}
        onclick={() => terminal.disconnect()}>Disconnect</Button>
      <Button id="reset-button" variant="toolbar" disabled={session.phase === "connecting"}
        title="Discard this session and open a fresh workspace" onclick={restart}>Reset session</Button>
    </div>
  </div>
  {#if session.message}
    <Banner id="session-banner" messageId="session-message">
      {session.message}
      {#snippet action()}
        {#if session.canReconnect}
          <Button id="reconnect-button" variant="banner" onclick={() => terminal.reconnect()}>
            Reconnect <span aria-hidden="true">↗</span>
          </Button>
        {:else if session.phase === "disconnected"}
          <Button variant="banner" onclick={restart}>Start new session</Button>
        {/if}
      {/snippet}
    </Banner>
  {/if}
  <div class="min-h-0 flex-1 overflow-hidden pt-3.5 pr-1.75 pb-2.5 pl-3 desktop:pt-5 desktop:pr-3.5 desktop:pb-3 desktop:pl-4.5 wide:pl-6">
    <div id="terminal" class="size-full outline-none" role="region" aria-label="Interactive Bash terminal"
      tabindex="-1" {@attach (host) => terminal.attach(host, environment, onTerminalError)}></div>
  </div>
  <TerminalStatus {session} />
</section>
