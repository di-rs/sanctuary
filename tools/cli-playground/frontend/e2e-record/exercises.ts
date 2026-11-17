import { z } from "zod";
import type { Argument, Command } from "../src/catalog";

const exercise = z.strictObject({
  args: z.array(z.string()),
  stdin: z.string().optional(),
  contains: z.string().optional(),
  exit: z.int().min(0).max(255).default(0),
  check: z.string().optional(),
  ready: z.string().optional(),
  keys: z.array(z.string()).optional(),
});
export const recipe = z.strictObject({
  setup: z.string().optional(),
  cases: z.array(exercise).min(1),
});
export type Exercise = z.infer<typeof exercise>;

function spellings(arg: Argument): string[] {
  return [
    ...(arg.long ? ["--" + arg.long] : []),
    ...(arg.short ? ["-" + arg.short] : []),
    ...arg.aliases,
  ];
}

function optionKey(arg: Argument): string {
  return [...arg.owner, spellings(arg)[0]].join(" ");
}

// Each recipe demonstrates one semantic use. Replay the same inputs with the
// other advertised spellings so adding an alias does not require another recipe.
export function exercises(root: Command, cases: Exercise[]): Exercise[] {
  const required = new Set<string>();
  const visited = new Set([""]);
  const automatic: Exercise[] = [];
  function visit(command: Command, path: string[]) {
    required.add(path.join(" "));
    for (const arg of command.args) {
      const names = spellings(arg);
      if (arg.action === "help" || arg.action === "version") {
        for (const flag of names) {
          automatic.push({
            args: [...path, flag],
            exit: 0,
            contains: arg.action === "help" ? "Usage:" : root.name,
          });
        }
      } else if (names.length) {
        required.add(optionKey(arg));
      }
    }
    for (const child of command.subcommands) {
      if (child.name !== "help") visit(child, [...path, child.name]);
    }
  }
  visit(root, []);
  const result: Exercise[] = [];
  for (const item of cases) {
    let command = root;
    let index = 0;
    const path: string[] = [];
    while (index < item.args.length) {
      const child = command.subcommands.find((candidate) => candidate.name === item.args[index]);
      if (!child) break;
      command = child;
      path.push(child.name);
      index++;
    }
    visited.add(path.join(" "));
    const alternatives = new Map<number, string[]>();
    for (; index < item.args.length; index++) {
      const token = item.args[index]!;
      if (token === "--") break;
      const arg = command.args.find((candidate) => spellings(candidate).includes(token));
      if (!arg) continue;
      if (arg.action === "help" || arg.action === "version") {
        throw new Error(
          "Help and version are recorded automatically. Supply a behavioral example.",
        );
      }
      visited.add(optionKey(arg));
      alternatives.set(index, [token, ...spellings(arg).filter((flag) => flag !== token)]);
      index += arg.num_args.min;
    }
    const count = Math.max(1, ...Array.from(alternatives.values(), (flags) => flags.length));
    for (let variant = 0; variant < count; variant++) {
      result.push({
        ...item,
        args: item.args.map((token, i) => alternatives.get(i)?.[variant] ?? token),
      });
    }
  }
  const missing = [...required].filter((key) => !visited.has(key));
  if (missing.length)
    throw new Error(
      `${root.name} lacks browser examples for ${missing.map((key) => key || "<default>").join(", ")}`,
    );
  return [...result, ...automatic];
}
