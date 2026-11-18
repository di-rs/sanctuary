<script lang="ts">
  import { runnable, type Environment, type RunnableEnvironment } from "../services/environment";
  import Banner from "../ui/Banner.svelte";
  import Button from "../ui/Button.svelte";

  let { active, latest, restart }: {
    active: RunnableEnvironment;
    latest: Environment;
    restart: () => void;
  } = $props();
  const build = $derived(latest.build);
  const updated = $derived(runnable(latest) && latest.revision !== active.revision);
</script>

{#if updated || (build && build.state !== "ready")}
  <Banner id="build-banner">
    {#if build?.state === "building"}
      Building commit <code>{build.sha.slice(0, 7)}</code>.
    {:else if build?.state === "failed"}
      Latest preview failed for <code>{build.sha.slice(0, 7)}</code>.
    {:else if build?.state === "cancelled"}
      Latest build was cancelled for <code>{build.sha.slice(0, 7)}</code>.
    {:else if build?.state === "empty"}
      No affected CLIs in commit <code>{build.sha.slice(0, 7)}</code>.
    {:else if updated && latest.sha}
      A new build is ready for <code>{latest.sha.slice(0, 7)}</code>.
    {/if}
    {#if build?.state !== "ready" && build?.state !== "building"}
      {#if updated && latest.sha}
        The last successful build is <code>{latest.sha.slice(0, 7)}</code>.
      {:else}
        You're using the last successful build.
      {/if}
    {/if}
    Your terminal remains on <code>{active.sha.slice(0, 7)}</code>.
    {#snippet action()}
      {#if updated}
        <Button variant="banner" onclick={restart}
          title="Discard this workspace and start a new terminal with the latest runnable build">Switch to latest build</Button>
      {/if}
    {/snippet}
  </Banner>
{/if}
