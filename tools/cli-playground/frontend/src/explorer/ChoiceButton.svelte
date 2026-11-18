<script lang="ts">
  import type { HTMLButtonAttributes } from "svelte/elements";
  import type { Change } from "./catalog-diff";

  type Props = Omit<HTMLButtonAttributes, "children"> & {
    label: string;
    query?: string;
    description?: string;
    change?: Change;
    valueLabel?: string;
    suffix?: string;
  };
  let {
    label, query = "", description, change, valueLabel, suffix, class: className, ...attributes
  }: Props = $props();
  const parts = $derived(query ? label.split(query) : [label]);
</script>

<button
  type="button"
  data-change={change}
  class={["w-full border border-neutral-800 bg-surface p-3 text-left wrap-anywhere text-ink enabled:hover:border-neutral-500 enabled:hover:bg-neutral-800", className]}
  {...attributes}
>
  <span class="flex flex-wrap items-baseline gap-2 text-sm">
    <code>
      {#each parts as part, index}
        {#if index > 0}<mark class="bg-neutral-600 text-white underline underline-offset-3">{query}</mark>{/if}{part}
      {/each}
    </code>
    {#if valueLabel}<span class="font-mono text-[11px] text-subtle">{valueLabel}</span>{/if}
    {#if change === "added" || change === "changed"}
      <span class="font-mono text-[11px] whitespace-nowrap text-detail">{change === "added" ? "+ Added" : "~ Changed"}</span>
    {/if}
    {#if suffix}<span aria-hidden="true" class="ml-auto text-subtle">{suffix}</span>{/if}
  </span>
  {#if description}
    <span class="mt-1 block text-[13px] leading-relaxed text-detail">{description.split("\n")[0]}</span>
  {/if}
</button>
