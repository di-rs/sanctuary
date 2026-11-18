<script lang="ts">
  import type { Environment, EnvironmentError } from "../services/environment";
  import Button from "../ui/Button.svelte";

  let { failure, pendingBuild, restart }: {
    failure: EnvironmentError | null;
    pendingBuild: Environment | undefined;
    restart: () => void;
  } = $props();
  const titles = {
    building: "This preview is building.",
    failed: "The latest preview failed.",
    empty: "No affected CLIs.",
    cancelled: "The latest build was cancelled.",
    ready: "No runnable build is available.",
  };
  const loading = $derived(!pendingBuild && !failure);
  const build = $derived(pendingBuild?.build);
  const heading = "my-4.5 text-[clamp(26px,4vw,40px)] leading-tight tracking-[-1.2px]";
  const description = "max-w-[500px] text-[13px] leading-relaxed text-muted";
</script>

<svelte:head><title>cli-playground</title></svelte:head>
<section
  id={failure ? "error-view" : loading ? "loading-view" : "preview-state"}
  class="mx-auto mt-[10vh] max-w-[760px] p-6 desktop:mt-[16vh] desktop:p-7.5"
  role={failure ? "alert" : undefined}
  aria-live={failure ? undefined : "polite"} aria-busy={loading}
>
  {#if failure}
    <span>PLAYGROUND UNAVAILABLE</span>
    <h1 id="error-title" class={heading}>{failure.title}</h1>
    <p id="error-message" class={description}>{failure.message}</p>
    {#if failure.retryable}
      <Button id="retry-button" variant="primary" onclick={restart}>Try again ↗</Button>
    {/if}
  {:else if pendingBuild}
    <span>PULL REQUEST #{pendingBuild.pr}</span>
    <h1 class={heading}>{titles[build?.state ?? "ready"]}</h1>
    {#if build}
      <p class={description}>
        Commit <code>{build.sha.slice(0, 7)}</code>.
        {#if build.state === "building"}
          This page will open a terminal when the build is ready.
        {:else if build.state === "empty"}
          This revision does not include CLI changes to try.
        {:else}
          Check the build details on the pull request. This page checks for updates automatically.
        {/if}
      </p>
    {/if}
    <Button onclick={restart}>Refresh status</Button>
  {:else}
    <span>PREPARING WORKSPACE</span>
    <h1 class={heading}>Opening your playground<span class="motion-safe:animate-pulse">.</span></h1>
    <p class={description}>Getting this build ready.</p>
  {/if}
</section>
