<script lang="ts">
  import type { Context } from "./command-context";
  import { flagNames, flagText } from "./shell";
  import ArgumentUsage from "./ArgumentUsage.svelte";
  import ChoiceButton from "./ChoiceButton.svelte";

  let { context, editable, draft, replaceLine }: {
    context: Context;
    editable: boolean;
    draft: string;
    replaceLine: (value: string) => void;
  } = $props();
  const node = $derived(context.node);
  const hasCommands = $derived(context.kind === "commands" && context.choices.length > 0);
  const showUsage = $derived(!context.query && !hasCommands);
  const removed = $derived([
    ...(node?.args ?? []).filter((row) => row.change === "removed").map(({ argument }) => ({
      name: flagNames(argument).long || argument.id, help: argument.help,
    })),
    ...(node?.children ?? []).filter((child) => child.change === "removed").map(({ command }) => ({
      name: command.name, help: command.about,
    })),
  ]);
</script>

{#snippet heading(text: string)}
  <h2 class="mt-6 mb-2.5 text-[13px] font-medium text-detail">{text}</h2>
{/snippet}

{#if node}
  <p class="mb-5 text-sm leading-relaxed text-detail">{node.command.about}</p>
  {#if showUsage}<ArgumentUsage {node} cli={context.cli} />{/if}
{/if}
{#if context.endOfOptions}
  <p>Options end at <code>--</code>. Remove it to add flags.</p>
{/if}
{#if context.kind === "value" && context.pending}
  {@const argument = context.pending.argument}
  {@render heading(`Value for ${flagNames(argument).long || argument.id}`)}
  <p>{argument.help} Type a value in the terminal{context.choices.length ? " or choose below." : "."}</p>
{:else if context.choices.length}
  {@render heading(hasCommands ? "Commands" : "Matching flags")}
{/if}
{#if context.choices.length}
  <div class="grid gap-2">
    {#each context.choices as choice}
      <ChoiceButton
        label={choice.label}
        aria-label={`Complete ${choice.label}`}
        description={choice.description}
        query={context.query}
        change={choice.change}
        suffix="↗"
        disabled={!editable}
        onclick={() => replaceLine(choice.value)}
      />
    {/each}
  </div>
{/if}
{#if showUsage && context.kind !== "value" && context.flags.length}
  {@render heading("Flags")}
  <div class="grid gap-2.5" role="group" aria-label="Flags">
    {#each context.flags as { argument, change }}
      {@const { short, long } = flagNames(argument)}
      {@const used = context.used.includes(argument.id)}
      <ChoiceButton
        label={[short, long].filter(Boolean).join(", ")}
        aria-label={`Insert ${long || short}`}
        description={argument.help}
        valueLabel={argument.num_args.max !== 0 ? argument.value_names.join(" ") || "VALUE" : undefined}
        {change}
        suffix={used ? "✓" : "+"}
        disabled={!editable || used}
        onclick={() => replaceLine(draft.trimEnd() + flagText(argument))}
      />
    {/each}
  </div>
{/if}
{#if removed.length}
  <details class="mt-2 mb-1 text-xs leading-relaxed">
    <summary class="list-none">Removed in this PR · {removed.length}</summary>
    {#each removed as item}<p class="whitespace-pre-line"><code>{item.name}</code> — {item.help}</p>{/each}
  </details>
{/if}
