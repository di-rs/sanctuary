<script lang="ts">
  import type { HTMLButtonAttributes } from "svelte/elements";

  type Variant = "toolbar" | "banner" | "action" | "primary";
  let { variant = "action", children, class: className, ...attributes }:
    HTMLButtonAttributes & { variant?: Variant } = $props();
  const styles: Record<Variant, string> = {
    toolbar: "min-h-[30px] py-1.5 text-[9px] text-subtle enabled:hover:text-white desktop:min-h-0 desktop:text-[10px]",
    banner: "border border-neutral-600 px-2.5 py-1.5 text-[10px] enabled:hover:bg-neutral-800",
    action: "mt-3.5 border border-neutral-600 px-4 py-2.5 text-xs enabled:hover:bg-neutral-800",
    primary: "mt-3.5 border border-neutral-600 bg-ink px-4 py-2.5 text-xs text-panel enabled:hover:bg-white",
  };
</script>

<button type="button" class={["whitespace-nowrap", styles[variant], className]} {...attributes}>
  {@render children?.()}
</button>
