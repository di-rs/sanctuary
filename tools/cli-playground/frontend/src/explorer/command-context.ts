import type { ArgumentView, Change, CommandView } from "./catalog-diff";
import { flagNames, quoteToken as quote } from "./shell";

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
  change?: Change;
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

const isCurrent = ({ change }: { change: Change }) => change !== "removed";
const commandNames = ({ command }: CommandView) => [command.name, ...command.aliases];

export function commandContext(
  text: string,
  names: string[],
  commands: ReadonlyMap<string, CommandView>,
): Context {
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
        description: commands.get(name)?.command.about ?? "",
        value: replace(first, name),
      }));
    return {
      ...empty,
      query: cli,
      choices,
      kind: choices.length && parsed.length <= 1 ? "clis" : "missing",
    };
  }
  const root = commands.get(cli);
  if (!root) return { ...empty, cli, kind: "unsupported" };
  let node = root;
  let children = node.children.filter(isCurrent);
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
    if (!endOfOptions && token.value.startsWith("-")) {
      const name = token.value.split("=")[0];
      const flag = node.args.find(
        (row) =>
          isCurrent(row) &&
          (Object.values(flagNames(row.argument)).includes(name) ||
            row.argument.aliases.some(
              (alias) => `${alias.length === 1 ? "-" : "--"}${alias}` === name,
            )),
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
    const child = operands
      ? undefined
      : children.find((item) => commandNames(item).includes(token.value));
    if (child) {
      node = child;
      children = node.children.filter(isCurrent);
      continue;
    }
    if ((operands || !children.length) && node.args.some((row) => row.argument.index !== null)) {
      operands = true;
      continue;
    }
    partial = token;
    break;
  }
  const flags = endOfOptions
    ? []
    : node.args.filter((row) => isCurrent(row) && (row.argument.short || row.argument.long));
  const query = partial?.value ?? "";
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
        const { long, short } = flagNames(row.argument);
        const name = [long, short].find((name) => name && name.includes(query));
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
    choices = (endOfOptions ? [] : children)
      .filter((child) => !query || commandNames(child).some((name) => name.includes(query)))
      .map((child) => ({
        label: child.command.name,
        description: child.command.about,
        value: replace(partial, child.command.name),
        change: child.change,
      }));
    if (!choices.length && !partial) kind = "flags";
  }
  choices = choices.filter((choice) => choice.value !== "");
  if (partial && (!choices.length || parsed.at(-1) !== partial)) kind = "missing";
  return { cli, node, query, kind, choices, flags, used, pending, endOfOptions };
}
