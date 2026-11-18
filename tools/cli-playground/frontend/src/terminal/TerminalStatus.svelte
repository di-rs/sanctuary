<script lang="ts">
  import type { SessionState } from "./session";
  let { session }: { session: SessionState } = $props();
</script>

<div class="flex min-h-[30px] items-center gap-3 border-t border-line px-3 font-mono text-[9px] text-muted desktop:px-4.5 wide:gap-4.5 wide:px-6">
  <div id="connection-status" role="status" aria-live="polite" data-state={session.phase}
    class="flex items-center gap-1.75 whitespace-nowrap text-neutral-300 before:size-1 before:border before:border-muted data-[state=connected]:before:border-neutral-300 data-[state=connected]:before:bg-neutral-300">
    <span id="status-label">{session.label}</span>
  </div>
  <span class="hidden desktop:inline">/workspace</span>
  {#if session.absoluteDeadline}
    <time id="session-expiry" class="hidden wide:inline" datetime={session.absoluteDeadline}
      title={new Date(session.absoluteDeadline).toLocaleString()}>Temporary session</time>
  {/if}
  <div class="ml-auto flex gap-4 text-[8px] desktop:text-[9px]">
    <span class="hidden wide:inline"><kbd>↑</kbd> history</span>
    <span><kbd>Ctrl C</kbd> stop</span>
  </div>
</div>
