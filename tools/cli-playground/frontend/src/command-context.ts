import {
  compareCommand,
  quoteToken as quote,
  type Catalog,
  type CommandView,
  type ArgumentView,
} from "./catalog";

interface Token {
  value: string;
  start: number;
  end: number;
}
// Deliberately a single simple shell command, not a shell evaluator. Expansions,
// pipes, redirects and compound syntax get no potentially misleading suggestions.
export function tokens(text: string): Token[] | null {
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1f\x7f-\x9f]/u.test(text)) return null;
  const result: Token[] = [];
  let value = "",
    start = -1,
    quoted = "";
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (!quoted && /\s/.test(c)) {
      if (start >= 0) result.push({ value, start, end: i });
      value = "";
      start = -1;
      continue;
    }
    if (start < 0) start = i;
    if (c === quoted) {
      quoted = "";
      continue;
    }
    if (!quoted && (c === "'" || c === '"')) {
      quoted = c;
      continue;
    }
    if (c === "\\" && quoted !== "'") {
      if (++i >= text.length) return null;
      value += text[i];
      continue;
    }
    if (quoted !== "'" && /[$`]/.test(c)) return null;
    if (!quoted && /[|;&<>()\n\r]/.test(c)) return null;
    value += c;
  }
  if (quoted) return null;
  if (start >= 0) result.push({ value, start, end: text.length });
  return result;
}
export interface Suggestion {
  label: string;
  description: string;
  value: string;
  change?: string;
}
export interface Context {
  cli: string;
  node: CommandView | null;
  query: string;
  kind: "clis" | "commands" | "flags" | "value" | "missing" | "unsupported";
  choices: Suggestion[];
  flags: ArgumentView[];
  used: string[];
  endOfOptions?: boolean;
  pending?: ArgumentView;
}
export function commandContext(text: string, names: string[], catalog: Catalog | null): Context {
  const empty: Context = {
    cli: "",
    node: null,
    query: "",
    kind: "clis",
    choices: [],
    flags: [],
    used: [],
  };
  const parsed = tokens(text);
  if (!parsed) return { ...empty, kind: "unsupported" };
  const first = parsed[0];
  const cli = first?.value.replace(/^\/opt\/artifact\//, "") ?? "";
  const replace = (token: Token | undefined, value: string) => {
    try {
      const quoted = quote(value);
      return token
        ? text.slice(0, token.start) + quoted + " " + text.slice(token.end).trimStart()
        : text.trimEnd() + (text.trim() ? " " : "") + quoted + " ";
    } catch {
      return "";
    }
  };
  if (!first || !names.includes(cli)) {
    const choices = names
      .filter((name) => name.includes(cli))
      .map((name) => ({
        label: name,
        description: catalog?.clis.find((item) => item.name === name)?.head.command.about ?? "",
        value: replace(first, name),
      }));
    return {
      ...empty,
      query: cli,
      choices,
      kind: choices.length && parsed.length <= 1 ? "clis" : "missing",
    };
  }
  const entry = catalog?.clis.find((item) => item.name === cli);
  if (!entry) return { ...empty, cli, kind: "unsupported" };
  let node = compareCommand(entry.head.command, entry.base?.command ?? null, entry.comparison);
  let pending: ArgumentView | undefined;
  let remaining = 0;
  let operands = false;
  let endOfOptions = false;
  const used: string[] = [];
  let partial: Token | undefined;
  let kind: Context["kind"] = "commands";
  for (const token of parsed.slice(1)) {
    if (remaining > 0) {
      remaining--;
      if (!remaining) pending = undefined;
      continue;
    }
    if (token.value === "--") {
      operands = true;
      endOfOptions = true;
      continue;
    }
    const flags = node.args.filter((row) => row.change !== "removed");
    if (!endOfOptions && token.value.startsWith("-")) {
      const name = token.value.split("=")[0];
      const flag = flags.find((row) =>
        [
          row.argument.long && `--${row.argument.long}`,
          row.argument.short && `-${row.argument.short}`,
          ...row.argument.aliases.map((alias) => `${alias.length === 1 ? "-" : "--"}${alias}`),
        ].includes(name),
      );
      if (!flag) {
        partial = token;
        kind = "flags";
        break;
      }
      used.push(flag.argument.id);
      if (flag.argument.num_args.max !== 0 && !token.value.includes("=")) {
        remaining = Math.max(1, flag.argument.num_args.min);
        pending = flag;
      }
      continue;
    }
    const child = node.children.find(
      (item) =>
        item.change !== "removed" &&
        [item.command.name, ...item.command.aliases].includes(token.value),
    );
    if (!operands && child) {
      node = child;
      continue;
    }
    if (!operands && node.children.some((child) => child.change !== "removed")) {
      partial = token;
      kind = "commands";
      break;
    }
    if (node.args.some((row) => row.argument.index !== null)) {
      operands = true;
      continue;
    }
    partial = token;
    kind = "commands";
    break;
  }
  const flags = node.args.filter(
    (row) => !endOfOptions && row.change !== "removed" && (row.argument.short || row.argument.long),
  );
  const query = partial?.value ?? "";
  const children = node.children.filter(
    (child) =>
      !endOfOptions &&
      child.change !== "removed" &&
      (!query ||
        [child.command.name, ...child.command.aliases].some((name) => name.includes(query))),
  );
  let choices: Suggestion[] = [];
  if (pending) {
    kind = "value";
    choices = pending.argument.possible_values.map((value) => ({
      label: value,
      description: "",
      value: replace(undefined, value),
    }));
  } else if (kind === "flags") {
    choices = flags
      .filter((row) => !used.includes(row.argument.id))
      .flatMap((row) => {
        const names = [
          row.argument.long ? `--${row.argument.long}` : "",
          row.argument.short ? `-${row.argument.short}` : "",
        ].filter(Boolean);
        const name = names.find((name) => name.includes(query));
        return name
          ? [
              {
                label: name,
                description: row.argument.help,
                value: replace(partial, name),
                change: row.change,
              },
            ]
          : [];
      });
  } else {
    choices = children.map((child) => ({
      label: child.command.name,
      description: child.command.about,
      value: replace(partial, child.command.name),
      change: child.change,
    }));
    if (!children.length && !partial) kind = "flags";
  }
  choices = choices.filter((choice) => choice.value !== "");
  if (partial && (!choices.length || parsed.at(-1) !== partial)) kind = "missing";
  return { cli, node, query, kind, choices, flags, used, pending, endOfOptions };
}
