<script lang="ts">
  import type { Snippet } from "svelte";

  let { id, messageId, children, action }: {
    id: string;
    messageId?: string;
    children: Snippet;
    action?: Snippet;
  } = $props();
</script>

<div {id} role="status" class="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-700 bg-surface px-3 py-2.5 desktop:flex-nowrap desktop:gap-4.5 desktop:px-6">
  <p id={messageId} class="text-[10px] leading-relaxed text-detail desktop:text-[11px]">{@render children()}</p>
  {@render action?.()}
</div>
