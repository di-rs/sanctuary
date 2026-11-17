<script lang="ts">
  import { commandContext } from "./command-context";
  import { commandText, quoteToken, type Catalog } from "./catalog";
  import type { Draft } from "./terminal/draft";
  import { files, shellExamples } from "./examples";
  let {
    clis,
    selectedCli = $bindable(),
    catalog,
    catalogLoading,
    connected,
    draft,
    replaceLine,
    retry,
  }: {
    clis: string[];
    selectedCli: string;
    catalog: Catalog | null;
    catalogLoading: boolean;
    connected: boolean;
    draft: Draft;
    replaceLine: (value: string) => void;
    retry: () => void;
  } = $props();
  // Keep the last reference while the shell runs. A quick paste and Enter
  // can span several PTY frames without ever becoming a draft to edit.
  const promptText = $derived(connected && draft.ready ? draft.text : null);
  let referenceText = $state("");
  let waiting = $state(true);
  $effect(() => {
    const text = promptText;
    const timer = setTimeout(() => {
      waiting = text === null;
      if (text !== null) referenceText = text;
    }, 120);
    return () => clearTimeout(timer);
  });
  const context = $derived(commandContext(referenceText, clis, catalog));
  const editable = $derived(promptText !== null && promptText === referenceText);
  $effect(() => {
    if (context.cli) selectedCli = context.cli;
  });
  function apply(value: string) {
    // Both catalog and shell content are untrusted. No pasted control bytes.
    if (
      [...value].some(
        (c) =>
          c.charCodeAt(0) < 32 ||
          (c.charCodeAt(0) >= 127 && c.charCodeAt(0) <= 159),
      )
    )
      return;
    replaceLine(value);
  }
  function addFlag(spelling: string) {
    apply(`${draft.text.trimEnd()} ${quoteToken(spelling)} `);
  }
</script>

{#snippet matched(label: string)}
  {#if context.query}{#each label.split(context.query) as part, index}{#if index > 0}<mark
          >{context.query}</mark
        >{/if}{part}{/each}{:else}{label}{/if}
{/snippet}

<div class="builder-header">
  <span>Command builder</span>
  {#if context.cli || referenceText}<button
      type="button"
      disabled={!editable}
      onclick={() => apply("")}
      title="Clear the draft and choose another CLI">All CLIs</button
    >{:else}<span class="cli-total">{clis.length} {clis.length === 1 ? "CLI" : "CLIs"}</span>{/if}
</div>
<div class="explorer-scroll builder">
  {#if context.cli}
    <nav class="builder-path" aria-label="Current command">
      <button
        type="button"
        disabled={!editable}
        onclick={() => apply(commandText(context.cli, []))}
        >{context.cli}</button
      >
      {#each context.node?.path ?? [] as part, index}<span>/</span><button
          type="button"
          disabled={!editable}
          onclick={() =>
            apply(
              commandText(context.cli, context.node!.path.slice(0, index + 1)),
            )}>{part}</button
        >{/each}
    </nav>
  {/if}
  {#if catalogLoading}<p class="builder-note">Loading command reference…</p>
  {:else if !catalog}<div class="catalog-status">
      Command reference unavailable <button type="button" onclick={retry}
        >Retry</button
      >
    </div>{/if}
  {#if context.kind === "missing"}
    <p class="builder-empty" role="status">No command found</p>
    <p class="builder-note">
      Edit the command in the terminal, or choose All CLIs to start again.
    </p>
  {:else if context.kind === "unsupported"}
    <p class="builder-empty">No command reference</p>
    <p class="builder-note">
      Suggestions cover a single command. Keep using the terminal for pipes,
      redirects and shell expressions.
    </p>
  {:else}
    {#if context.kind === "clis"}
      <p class="builder-intro">Choose a CLI or start typing.</p>
      <div class="cli-grid" aria-label="CLIs">
        {#each context.choices as choice}<button
            type="button"
            disabled={!editable}
            aria-label={`Insert ${choice.label}`}
            title={choice.description}
            onclick={() => apply(choice.value)}
            ><code>{@render matched(choice.label)}</code></button
          >{/each}
      </div>
    {:else}
      {#if context.node}<p class="command-about">
          {context.node.command.about}
        </p>{/if}
      {#if context.node && !context.query && !(context.kind === "commands" && context.choices.length)}
        {@const operands = context.node.args
          .filter(
            (row) => row.argument.index !== null && row.change !== "removed",
          )
          .sort((a, b) => a.argument.index! - b.argument.index!)}
        {#if operands.length}
          <div class="argument-usage" aria-label="Argument usage">
            <code class="usage-pattern"
              >{[context.cli, ...context.node.path].join(
                " ",
              )}{#each operands as row}{@const arg = row.argument}{@const name =
                  (
                    arg.value_names.join(" ") || arg.id
                  ).toLowerCase()}{@const repeated =
                  arg.num_args.max === null ||
                  arg.num_args.max > Math.max(1, arg.value_names.length)}<span
                  class="usage-operand"
                >
                  {" "}{arg.required ? "<" : "["}{name}{repeated
                    ? "…"
                    : ""}{arg.required ? ">" : "]"}</span
                >{/each}</code
            >
            {#each operands as row}
              <p class="usage-explanation">
                {#if operands.length > 1}<code
                    >{(
                      row.argument.value_names.join(" ") || row.argument.id
                    ).toLowerCase()}</code
                  >:
                {/if}{row.argument.help.split("\n")[0]}<span class="usage-note">
                  {" · "}{row.argument.required
                    ? "required"
                    : "optional"}{#if row.argument.default_values.length}
                    {" · defaults to "}<code
                      >{row.argument.default_values.join(", ")}</code
                    >{/if}</span
                >
              </p>
            {/each}
          </div>
        {/if}
      {/if}
      {#if context.endOfOptions}<p class="builder-note">Options end at <code>--</code>. Remove it to add flags.</p>{/if}
      {#if context.kind === "value"}
        <h2 class="builder-heading">
          Value for {context.pending?.argument.long
            ? `--${context.pending.argument.long}`
            : context.pending?.argument.id}
        </h2>
        <p class="builder-note">
          {context.pending?.argument.help} Type a value in the terminal{context
            .choices.length
            ? " or choose below."
            : "."}
        </p>
      {:else if context.choices.length}<h2 class="builder-heading">
          {context.kind === "commands" ? "Commands" : "Matching flags"}
        </h2>{/if}
      <div class="builder-choices">
        {#each context.choices as choice}
          <button
            type="button"
            disabled={!editable}
            aria-label={`Complete ${choice.label}`}
            onclick={() => apply(choice.value)}
          >
            <span class="choice-title"
              ><code>{@render matched(choice.label)}</code
              >{#if choice.change && choice.change !== "unchanged"}<span
                  class="badge"
                  >{choice.change === "added" ? "+ Added" : "~ Changed"}</span
                >{/if}<span class="choice-arrow" aria-hidden="true">↗</span
              ></span
            >
            {#if choice.description}<span class="choice-description"
                >{choice.description.split("\n")[0]}</span
              >{/if}
          </button>
        {/each}
      </div>
      {#if !context.query && context.kind !== "value" && !(context.kind === "commands" && context.choices.length)}
        {#if context.flags.length}<h2 class="builder-heading">Flags</h2>{/if}
        <div class="builder-flags">
          {#each context.flags as row}
            {@const arg = row.argument}
            {@const spelling = arg.long ? `--${arg.long}` : `-${arg.short}`}
            {@const used = context.used.includes(arg.id)}
            <div class="builder-flag" data-change={row.change}>
              <button
                type="button"
                class="flag-choice"
                aria-label={`Insert ${spelling}`}
                disabled={!editable || used}
                onclick={() => addFlag(spelling)}
              >
                <span class="choice-title"
                  ><code
                    >{[
                      arg.short ? `-${arg.short}` : "",
                      arg.long ? `--${arg.long}` : "",
                    ]
                      .filter(Boolean)
                      .join(", ")}</code
                  >{#if arg.num_args.max !== 0}<span class="value-label"
                      >{arg.value_names.join(" ") || "VALUE"}</span
                    >{/if}<span class="choice-arrow">{used ? "✓" : "+"}</span
                  ></span
                >
                {#if row.change !== "unchanged"}<span class="badge"
                    >{row.change === "added" ? "+ Added" : "~ Changed"}</span
                  >{/if}
                <span class="choice-description">{arg.help.split("\n")[0]}</span
                >
              </button>
            </div>
          {/each}
        </div>
      {/if}
    {/if}
  {/if}
  {#if context.node && !["missing", "unsupported"].includes(context.kind)}
    {@const removed = [
      ...context.node.args
        .filter((row) => row.change === "removed")
        .map((row) => ({
          name: row.argument.long ? `--${row.argument.long}` : row.argument.id,
          help: row.argument.help,
        })),
      ...context.node.children
        .filter((child) => child.change === "removed")
        .map((child) => ({
          name: child.command.name,
          help: child.command.about,
        })),
    ]}
    {#if removed.length}<details class="builder-details removed-section">
        <summary>Removed in this PR · {removed.length}</summary
        >{#each removed as item}<p>
            <code>{item.name}</code> — {item.help}
          </p>{/each}
      </details>{/if}
  {/if}
  <div class="explorer-extras">
    <details class="workspace-details">
      <summary>Sample files</summary>
      <ul class="file-list">
        {#each files as file}<li>
            <button
              type="button"
              disabled={!editable}
              aria-label={`Insert command to read ${file}`}
              onclick={() => apply(`cat ${quoteToken(file)}`)}>{file}</button
            >
          </li>{/each}
      </ul>
    </details>
    <details class="shell-details">
      <summary>Shell essentials</summary>{#each shellExamples as example}<button
          type="button"
          class="shell-example"
          disabled={!editable}
          aria-label={`Insert ${example.display}: ${example.label}`}
          onclick={() => apply(example.command)}
          ><span>{example.label}</span><code>{example.display}</code></button
        >{/each}
    </details>
  </div>
  <p class="builder-footnote" role="status">
    {#if !connected}Connect to build a command.
    {:else if waiting}Waiting for a shell prompt…
    {:else}Clicks edit your command. <kbd>Enter</kbd> runs it.{/if}
  </p>
</div>
