<script lang="ts">
  import { createQuery } from "@tanstack/svelte-query";
  import { Debounced, watch } from "runed";
  import { onDestroy } from "svelte";
  import type { RunnableEnvironment } from "../services/environment";
  import { catalogQuery } from "../services/queries";
  import type { Draft } from "../terminal/draft";
  import { indexCatalog } from "./catalog-diff";
  import { commandContext } from "./command-context";
  import { commandText } from "./shell";
  import ChoiceButton from "./ChoiceButton.svelte";
  import CommandReference from "./CommandReference.svelte";
  import WorkspaceExamples from "./WorkspaceExamples.svelte";

  let { environment, connected, draft, replaceLine }: {
    environment: RunnableEnvironment;
    connected: boolean;
    draft: Draft;
    replaceLine: (value: string) => void;
  } = $props();
  const catalog = createQuery(() => catalogQuery(environment));
  const commands = $derived(indexCatalog(catalog.data));
  const prompt = $derived(connected && draft.ready ? draft.text : null);
  const settledPrompt = new Debounced(() => prompt, 120);
  onDestroy(settledPrompt.cancel);
  let reference = $state("");
  let lastCli = $state("");
  const context = $derived(commandContext(reference, environment.clis, commands));
  const editable = $derived(prompt !== null && prompt === reference);

  // A paste followed by Enter can span several PTY frames. Keep the last settled
  // reference on screen while the program runs, but lock edits immediately.
  watch(() => settledPrompt.current, (text) => {
    if (text === null) return;
    reference = text;
    if (context.cli) lastCli = context.cli;
  });
</script>

<svelte:head><title>{lastCli || environment.clis[0]} / cli-playground</title></svelte:head>
<header class="flex items-center justify-between border-b border-line p-5 text-sm">
  <h2>Command builder</h2>
  {#if reference}
    <button type="button" class="text-[13px] text-neutral-300 underline underline-offset-4"
      disabled={!editable} onclick={() => replaceLine("")} title="Clear the draft and choose another CLI">All CLIs</button>
  {:else}
    <span class="font-mono text-xs text-subtle">{environment.clis.length} {environment.clis.length === 1 ? "CLI" : "CLIs"}</span>
  {/if}
</header>
<div class="min-h-0 flex-1 overflow-auto overscroll-contain px-5 py-4.5 text-[13px] leading-relaxed text-subtle [scrollbar-color:#444_transparent] [scrollbar-width:thin] motion-safe:[&_button:disabled]:[transition:opacity_0s_120ms]">
  {#if context.cli}
    {@const path = context.node?.path ?? []}
    <nav class="mb-3 flex flex-wrap items-center gap-2 font-mono text-[15px] text-ink" aria-label="Current command">
      {#each [context.cli, ...path] as part, index}
        {#if index > 0}<span class="text-neutral-500">/</span>{/if}
        <button type="button" class="py-0.5 underline-offset-4 enabled:hover:underline"
          disabled={!editable} onclick={() => replaceLine(commandText(context.cli, path.slice(0, index)))}>{part}</button>
      {/each}
    </nav>
  {/if}
  {#if catalog.isFetching}
    <p>Loading command reference…</p>
  {:else if !catalog.data}
    <p class="py-3">Command reference unavailable
      <button type="button" class="underline" onclick={() => void catalog.refetch()}>Retry</button>
    </p>
  {/if}
  {#if context.kind === "missing" || context.kind === "unsupported"}
    <p class="mt-4.5 mb-2 text-[17px] text-ink" role="status">{context.kind === "missing" ? "No command found" : "No command reference"}</p>
    <p>{context.kind === "missing"
      ? "Edit the command in the terminal, or choose All CLIs to start again."
      : "Suggestions cover a single command. Keep using the terminal for pipes, redirects and shell expressions."}</p>
  {:else if context.kind === "clis"}
    <p class="mb-4">Choose a CLI or start typing.</p>
    <div class="grid gap-2" role="group" aria-label="CLIs">
      {#each context.choices as choice}
        <ChoiceButton
          label={choice.label}
          query={context.query}
          title={choice.description}
          aria-label={`Insert ${choice.label}`}
          disabled={!editable}
          onclick={() => replaceLine(choice.value)}
        />
      {/each}
    </div>
  {:else}
    <CommandReference {context} {editable} {replaceLine} draft={draft.text} />
  {/if}
  <WorkspaceExamples {editable} {replaceLine} />
  <p class="text-xs leading-relaxed" role="status">
    {#if !connected}Connect to build a command.
    {:else if settledPrompt.current === null}Waiting for a shell prompt…
    {:else}Clicks edit your command. <kbd>Enter</kbd> runs it.{/if}
  </p>
</div>
