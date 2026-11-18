import { z } from "zod";

const token = z
  .string()
  .min(1)
  .max(128)
  // Control characters must never become terminal tokens.
  // eslint-disable-next-line no-control-regex
  .regex(/^[^\x00-\x20\x7f-\x9f]+$/);
const text = z.string().max(8192);
const argumentSchema = z.object({
  id: token,
  short: token.length(1).nullable(),
  long: token.nullable(),
  aliases: z.array(token),
  help: text,
  long_help: text.nullable(),
  value_names: z.array(text),
  default_values: z.array(text),
  possible_values: z.array(text),
  required: z.boolean(),
  index: z.int().positive().nullable(),
  num_args: z.object({ min: z.int().nonnegative(), max: z.int().nonnegative().nullable() }),
  action: z.string(),
  global: z.boolean(),
  owner: z.array(token),
});
export type Argument = z.infer<typeof argumentSchema>;
export interface Command {
  name: string;
  aliases: string[];
  about: string;
  long_about: string | null;
  usage: string;
  usage_override: string | null;
  args: Argument[];
  subcommands: Command[];
}
const commandSchema: z.ZodType<Command> = z.object({
  name: token,
  aliases: z.array(token),
  about: text,
  long_about: text.nullable(),
  usage: text,
  usage_override: text.nullable(),
  args: z.array(argumentSchema),
  subcommands: z.lazy(() => z.array(commandSchema)),
});
const cliSchema = z.object({ schema_version: z.literal(1), command: commandSchema });
const catalogSchema = z.object({
  schema_version: z.literal(1),
  head_sha: z.string().regex(/^[a-f0-9]{40}$/),
  base_sha: z.string().regex(/^[a-f0-9]{40}$/),
  clis: z.array(
    z.object({
      name: z.string().regex(/^[a-z][a-z0-9_-]{0,63}$/),
      binary_sha256: z.string().regex(/^[a-f0-9]{64}$/),
      head: cliSchema,
      base: cliSchema.nullable(),
      comparison: z.enum(["available", "added", "unavailable"]),
    }),
  ),
});
export type Catalog = z.infer<typeof catalogSchema>;
export type CliCatalog = Catalog["clis"][number];

export function parseCatalog(value: unknown, sha: string, names: string[]): Catalog {
  const catalog = catalogSchema.parse(value);
  if (
    catalog.head_sha !== sha ||
    catalog.clis.length !== names.length ||
    new Set(catalog.clis.map((cli) => cli.name)).size !== names.length ||
    catalog.clis.some(
      (cli) =>
        !names.includes(cli.name) ||
        cli.head.command.name !== cli.name ||
        (cli.base !== null) !== (cli.comparison === "available") ||
        (cli.base && cli.base.command.name !== cli.name),
    )
  ) {
    throw new Error("Catalog identity mismatch");
  }
  return catalog;
}

export async function loadCatalog(
  id: string,
  revision: string,
  sha: string,
  names: string[],
  signal: AbortSignal,
): Promise<Catalog | null> {
  const response = await fetch(
    `/api/environments/${encodeURIComponent(id)}/revisions/${encodeURIComponent(revision)}/catalog`,
    { signal },
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("Command reference unavailable");
  const value: unknown = await response.json();
  return value === null ? null : parseCatalog(value, sha, names);
}
