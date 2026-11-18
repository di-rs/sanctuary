<script lang="ts">
  import { files, shellExamples } from "./examples";
  import { quoteToken } from "./shell";

  let { editable, replaceLine }: { editable: boolean; replaceLine: (value: string) => void } = $props();
  const summaryStyle = "list-none py-2.5 text-[11px] text-detail hover:text-white";
</script>

<div class="mt-5 border-t border-line pt-2 text-[10px]">
  <details>
    <summary class={summaryStyle}>Sample files</summary>
    <ul class="mt-1 mb-3">
      {#each files as file}
        <li><button type="button" class="w-full py-1.5 text-left font-mono text-detail enabled:hover:text-white"
          disabled={!editable} aria-label={`Insert command to read ${file}`}
          onclick={() => replaceLine(`cat ${quoteToken(file)}`)}>{file}</button></li>
      {/each}
    </ul>
  </details>
  <details>
    <summary class={summaryStyle}>Shell essentials</summary>
    {#each shellExamples as { label, command }}
      <button type="button" class="block w-full py-2 text-left" disabled={!editable}
        aria-label={`Insert ${command}: ${label}`} onclick={() => replaceLine(command)}>
        <span class="mb-1 block text-muted">{label}</span><code class="wrap-anywhere text-ink">{command}</code>
      </button>
    {/each}
  </details>
</div>
