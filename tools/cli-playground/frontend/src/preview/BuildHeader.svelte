<script lang="ts">
  import type { Environment, RunnableEnvironment } from "../services/environment";

  let { environment, build, terminalAvailable }: {
    environment: RunnableEnvironment | null;
    build: Environment["build"] | undefined;
    terminalAvailable: boolean;
  } = $props();
</script>

<a class="fixed -top-20 left-4 z-50 bg-ink px-4.5 py-3 text-panel focus:top-3"
  href={terminalAvailable ? "#terminal" : "#main"}>
  Skip to {terminalAvailable ? "terminal" : "content"}
</a>
<header class="flex h-12 items-center justify-between gap-2.5 border-b border-line px-3.5 desktop:gap-5 desktop:px-5 wide:px-6">
  <div class="flex items-center gap-4 text-[11px] text-muted">
    <span class="text-[15px] font-medium tracking-[-0.6px] text-ink desktop:text-base">Sanctuary<span aria-hidden="true" class="text-muted">_</span></span>
    <span class="hidden text-neutral-600 desktop:inline">/</span>
    <span class="hidden desktop:inline">playground</span>
  </div>
  {#if environment}
    <div class="flex items-center gap-2 text-[10px] text-muted desktop:gap-4.5" aria-label="Build information">
      <a id="meta-pr" class="text-neutral-300 hover:text-white"
        href={environment.pr ? `https://github.com/di-rs/sanctuary/pull/${environment.pr}` : `https://github.com/di-rs/sanctuary/commit/${environment.sha}`} target="_blank" rel="noreferrer">
        {environment.pr ? `PR #${environment.pr}` : "Production"} ↗
      </a>
      <span class="hidden text-neutral-600 desktop:inline">/</span>
      <abbr id="meta-sha" class="font-mono no-underline" title={environment.sha}>{environment.sha.slice(0, 7)}</abbr>
      <span class="whitespace-nowrap text-neutral-300">Build {build?.state ?? "ready"}</span>
      <span class="hidden wide:inline">Link expires
        <time id="meta-expiry" datetime={environment.expiresAt.toISOString()} title={environment.expiresAt.toLocaleString()}>
          {environment.expiresAt.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
        </time>
      </span>
    </div>
  {/if}
</header>
