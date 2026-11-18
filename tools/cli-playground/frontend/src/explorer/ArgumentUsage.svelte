<script lang="ts">
  import type { CommandView } from "./catalog-diff";

  let { node, cli }: { node: CommandView; cli: string } = $props();
  const operands = $derived(node.args.flatMap(({ argument, change }) => {
    if (argument.index === null || change === "removed") return [];
    const name = (argument.value_names.join(" ") || argument.id).toLowerCase();
    const repeated = argument.num_args.max === null || argument.num_args.max > Math.max(1, argument.value_names.length);
    const label = name + (repeated ? "…" : "");
    return [{
      index: argument.index, name, argument,
      usage: argument.required ? `<${label}>` : `[${label}]`,
    }];
  }).sort((a, b) => a.index - b.index));
</script>

{#if operands.length}
  <div class="-mt-1 mb-5 wrap-anywhere" role="group" aria-label="Argument usage">
    <code class="block text-sm leading-relaxed text-neutral-200">{[cli, ...node.path].join(" ")}<span class="text-detail">{` ${operands.map((op) => op.usage).join(" ")}`}</span></code>
    {#each operands as { argument, name }}
      <p class="mt-1 text-xs leading-relaxed">
        {#if operands.length > 1}<code class="text-detail">{name}</code>: {/if}{argument.help.split("\n")[0]}
        <span class="text-muted"> · {argument.required ? "required" : "optional"}{#if argument.default_values.length} · defaults to <code class="text-detail">{argument.default_values.join(", ")}</code>{/if}</span>
      </p>
    {/each}
  </div>
{/if}
