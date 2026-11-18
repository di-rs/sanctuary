<script lang="ts">
  import { createQuery, useQueryClient } from "@tanstack/svelte-query";
  import { watch } from "runed";
  import { EnvironmentError, runnable, type RunnableEnvironment } from "../services/environment";
  import { environmentQuery } from "../services/queries";
  import BuildHeader from "./BuildHeader.svelte";
  import BuildBanner from "./BuildBanner.svelte";
  import PreviewState from "./PreviewState.svelte";
  import Workspace from "./Workspace.svelte";

  let { id }: { id: string | null } = $props();
  const client = useQueryClient();
  const options = $derived(environmentQuery(id));
  const metadata = createQuery(() => options);
  const latest = $derived(metadata.data);
  let active = $state.raw<RunnableEnvironment | null>(null);
  let terminalError = $state.raw<EnvironmentError | null>(null);

  // The first runnable revision owns the workspace until the user starts a fresh session.
  watch(() => latest, (environment) => {
    if (environment && runnable(environment)) active ??= environment;
  });

  const failure = $derived(
    terminalError ?? (metadata.isLoadingError ? describeError(metadata.error) : null),
  );
  function describeError(error: Error) {
    return error instanceof EnvironmentError
      ? error
      : new EnvironmentError(
          "Couldn't open the playground.",
          "Check your connection and try again. If the issue continues, open a newer preview from the pull request.",
          true,
        );
  }
  function restart() {
    terminalError = null;
    active = null;
    void client.resetQueries({ queryKey: options.queryKey, exact: true });
  }
  function terminalFailed() {
    terminalError = new EnvironmentError(
      "The terminal couldn't load.",
      "A required terminal feature is unavailable. Try again to reopen the playground.",
      true,
    );
  }
</script>

<BuildHeader environment={active} build={latest?.build} terminalAvailable={!!active && !failure} />
<main id="main" tabindex="-1" class="outline-none">
  {#if active && !failure}
    <div id="playground-view" class="flex h-[calc(100dvh-3rem)] flex-col">
      {#if latest}<BuildBanner {active} {latest} {restart} />{/if}
      <Workspace environment={active} {restart} onTerminalError={terminalFailed} />
    </div>
  {:else}
    <PreviewState {failure} pendingBuild={latest && !runnable(latest) ? latest : undefined} {restart} />
  {/if}
</main>
