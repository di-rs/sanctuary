import type { Argument, Catalog, CliCatalog, Command } from "../services/catalog";

export type Change = "added" | "changed" | "removed" | "unchanged";
export interface FieldChange {
  label: string;
  before: string;
  after: string;
}
export interface ArgumentView {
  argument: Argument;
  change: Change;
  fields: FieldChange[];
}
export interface CommandView {
  command: Command;
  path: string[];
  change: Change;
  fields: FieldChange[];
  args: ArgumentView[];
  children: CommandView[];
  count: number;
}

export function indexCatalog(
  catalog: Catalog | null | undefined,
): ReadonlyMap<string, CommandView> {
  const commands = new Map<string, CommandView>();
  for (const { name, head, base, comparison } of catalog?.clis ?? []) {
    commands.set(name, compareCommand(head.command, base?.command ?? null, comparison));
  }
  return commands;
}

const prose = (value: string) => value.replace(/\s+/g, " ").trim();
const list = (values: string[]) => [...values].sort().join(", ");
const show = (value: unknown) => (typeof value === "string" ? value : JSON.stringify(value));
function fields(before: Record<string, unknown>, after: Record<string, unknown>): FieldChange[] {
  return Object.keys(after).flatMap((label) =>
    show(before[label]) === show(after[label])
      ? []
      : [{ label, before: show(before[label]), after: show(after[label]) }],
  );
}
function properties(arg: Argument): Record<string, unknown> {
  return {
    "Short flag": arg.short,
    "Long flag": arg.long,
    Aliases: list(arg.aliases),
    Help: prose(arg.help),
    "Full help": prose(arg.long_help ?? ""),
    "Value names": arg.value_names,
    Defaults: arg.default_values,
    Choices: list(arg.possible_values),
    Required: arg.required,
    Position: arg.index,
    "Value count": arg.num_args,
    Action: arg.action,
    Global: arg.global,
    "Defined on": arg.owner,
  };
}
const spellings = (arg: Argument) => [
  ...arg.aliases,
  ...(arg.long ? [`--${arg.long}`] : []),
  ...(arg.short ? [`-${arg.short}`] : []),
];
function compareArgs(
  head: Argument[],
  base: Argument[],
  mode: CliCatalog["comparison"] | "removed",
): ArgumentView[] {
  if (mode !== "available")
    return head.map((argument) => ({
      argument,
      fields: [],
      change: mode === "unavailable" ? "unchanged" : mode,
    }));
  const remaining = new Set(base);
  const matches = new Map<Argument, Argument>();
  // Prefer stable IDs, then a unique shared public spelling. Internal renames alone are not changes.
  for (const arg of head) {
    const previous = base.find((old) => old.id === arg.id);
    if (previous) {
      matches.set(arg, previous);
      remaining.delete(previous);
    }
  }
  for (const arg of head.filter((item) => !matches.has(item))) {
    const candidates = [...remaining].filter((old) =>
      spellings(arg).some((name) => spellings(old).includes(name)),
    );
    const old = candidates[0];
    if (
      candidates.length === 1 &&
      old &&
      head.filter(
        (other) =>
          !matches.has(other) && spellings(other).some((name) => spellings(old).includes(name)),
      ).length === 1
    ) {
      matches.set(arg, old);
      remaining.delete(old);
    }
  }
  return [
    ...head.map((argument): ArgumentView => {
      const old = matches.get(argument);
      const changes = old ? fields(properties(old), properties(argument)) : [];
      return {
        argument,
        fields: changes,
        change: old ? (changes.length ? "changed" : "unchanged") : "added",
      };
    }),
    ...[...remaining].map((argument): ArgumentView => ({
      argument,
      fields: [],
      change: "removed",
    })),
  ];
}

export function compareCommand(
  command: Command,
  base: Command | null,
  mode: CliCatalog["comparison"] | "removed",
  path: string[] = [],
): CommandView {
  const changes = base ? fields(commandProperties(base), commandProperties(command)) : [];
  const args = compareArgs(command.args, base?.args ?? [], mode);
  const matches = new Map<Command, Command>();
  const remaining = new Set(base?.subcommands ?? []);
  for (const child of command.subcommands) {
    const previous = base?.subcommands.find((old) => old.name === child.name);
    if (previous) {
      matches.set(child, previous);
      remaining.delete(previous);
    }
  }
  const names = (child: Command) => [child.name, ...child.aliases];
  for (const child of command.subcommands.filter((item) => !matches.has(item))) {
    const candidates = [...remaining].filter((old) =>
      names(child).some((name) => names(old).includes(name)),
    );
    const previous = candidates[0];
    if (
      candidates.length === 1 &&
      previous &&
      command.subcommands.filter(
        (other) =>
          !matches.has(other) && names(other).some((name) => names(previous).includes(name)),
      ).length === 1
    ) {
      matches.set(child, previous);
      remaining.delete(previous);
    }
  }
  const children = command.subcommands.map((child) => {
    const previous = matches.get(child);
    return compareCommand(
      child,
      previous ?? null,
      mode === "available" && !previous ? "added" : mode,
      [...path, child.name],
    );
  });
  if (mode === "available")
    for (const old of remaining) {
      children.push(compareCommand(old, null, "removed", [...path, old.name]));
    }
  const change: Change =
    mode === "added" || mode === "removed" ? mode : changes.length ? "changed" : "unchanged";
  const ownArgs = args.filter(
    ({ argument, change: status }) =>
      status !== "unchanged" && (!argument.global || argument.owner.join("/") === path.join("/")),
  ).length;
  return {
    command,
    path,
    change,
    fields: changes,
    args,
    children,
    count:
      ownArgs +
      children.reduce((sum, child) => sum + child.count, 0) +
      (change !== "unchanged" ? 1 : 0),
  };
}

function commandProperties(command: Command): Record<string, unknown> {
  return {
    Name: command.name,
    Description: prose(command.about),
    "Full description": prose(command.long_about ?? ""),
    Aliases: list(command.aliases),
    // Generated usage follows Clap display order; only explicit usage overrides
    // represent an independent interface field.
    Usage: prose(command.usage_override ?? ""),
  };
}

export function visible(node: CommandView, query: string, changesOnly: boolean): boolean {
  if (changesOnly && node.count === 0) return false;
  const needle = query.toLowerCase().trim();
  return (
    !needle ||
    [
      node.command.name,
      node.command.about,
      ...node.path,
      ...node.command.aliases,
      ...node.args.flatMap(({ argument }) => [argument.id, argument.help, ...spellings(argument)]),
    ].some((value) => value.toLowerCase().includes(needle)) ||
    node.children.some((child) => visible(child, query, changesOnly))
  );
}
