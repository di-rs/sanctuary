import { describe, expect, it } from "vite-plus/test";
import { argument, catalog, command } from "../../testing/catalog";
import { compareCommand, visible } from "./catalog-diff";

describe("public interface comparison", () => {
  it("distinguishes added, removed and help-only changes with before and after details", () => {
    const cli = catalog("a".repeat(40)).clis[0];
    const tree = compareCommand(cli.head.command, cli.base!.command, cli.comparison);
    expect(tree.args.map((row) => [row.argument.id, row.change])).toEqual([
      ["help", "unchanged"],
      ["number", "changed"],
      ["format", "added"],
      ["old", "removed"],
    ]);
    expect(tree.args[1].fields).toEqual([
      { label: "Help", before: "Number output", after: "Number each line" },
    ]);
    expect(tree.count).toBe(3);
    expect(visible(tree, "--old", true)).toBe(true);
  });
  it("matches stable IDs and unique public spellings but never guesses a rename", () => {
    const base = command({ args: [argument({ id: "old-id", aliases: ["--assist"] })] });
    const internal = command({ args: [argument({ id: "new-id", aliases: ["--assist"] })] });
    expect(compareCommand(internal, base, "available").count).toBe(0);
    const renamed = command({ args: [argument({ id: "old-id", long: "assist", short: null })] });
    expect(compareCommand(renamed, base, "available").args[0].change).toBe("changed");
    const unknown = command({ args: [argument({ id: "another", long: "another", short: null })] });
    expect(compareCommand(unknown, base, "available").args.map((a) => a.change)).toEqual([
      "added",
      "removed",
    ]);
  });
  it("compares nested commands within their path and follows public command aliases", () => {
    const base = command({
      subcommands: [command({ name: "run", args: [] }), command({ name: "old", args: [] })],
    });
    const head = command({
      subcommands: [
        command({ name: "execute", aliases: ["run"], args: [] }),
        command({ name: "new", args: [] }),
      ],
    });
    const tree = compareCommand(head, base, "available");
    expect(tree.children.map((c) => [c.path, c.change])).toEqual([
      [["execute"], "changed"],
      [["new"], "added"],
      [["old"], "removed"],
    ]);
  });
  it("leaves shared spellings unpaired when either side has multiple candidates", () => {
    const flag = (id: string) => argument({ id, aliases: ["--shared"], short: null, long: null });
    const child = (name: string) => command({ name, aliases: ["shared"], args: [] });
    const base = command({
      args: [flag("old")],
      subcommands: [child("first-old"), child("second-old")],
    });
    const head = command({
      args: [flag("first-new"), flag("second-new")],
      subcommands: [child("new")],
    });
    const tree = compareCommand(head, base, "available");
    expect(tree.args.map(({ argument, change }) => [argument.id, change])).toEqual([
      ["first-new", "added"],
      ["second-new", "added"],
      ["old", "removed"],
    ]);
    expect(tree.children.map(({ command, change }) => [command.name, change])).toEqual([
      ["new", "added"],
      ["first-old", "removed"],
      ["second-old", "removed"],
    ]);
  });
  it("ignores ordering, whitespace and generated usage layout", () => {
    const base = command({
      args: [
        argument({ aliases: ["--a", "--b"], possible_values: ["x", "y"] }),
        argument({ id: "other", long: "other" }),
      ],
    });
    const head = structuredClone(base);
    head.args.reverse();
    head.args[1].aliases.reverse();
    head.args[1].possible_values.reverse();
    head.args[1].help = " Print\n help ";
    head.usage = "different layout";
    expect(compareCommand(head, base, "available").count).toBe(0);
  });
  it("detects full help, defaults, requiredness, arity, choices and explicit usage changes", () => {
    const base = command();
    const head = command({
      long_about: "Detailed usage",
      usage_override: "catr FILE",
      args: [
        argument({
          long_help: "More detail",
          default_values: ["text"],
          required: true,
          num_args: { min: 1, max: null },
          possible_values: ["text"],
        }),
      ],
    });
    const tree = compareCommand(head, base, "available");
    expect(tree.fields.map((field) => field.label)).toEqual(["Full description", "Usage"]);
    expect(tree.args[0].fields.map((field) => field.label)).toEqual([
      "Full help",
      "Defaults",
      "Choices",
      "Required",
      "Value count",
    ]);
  });
  it("counts inherited global changes once", () => {
    const arg = argument({ global: true });
    const base = command({ args: [arg], subcommands: [command({ name: "child", args: [arg] })] });
    const head = structuredClone(base);
    head.args[0].help = "Changed global";
    head.subcommands[0].args[0].help = "Changed global";
    const tree = compareCommand(head, base, "available");
    expect(tree.count).toBe(1);
    expect(tree.children[0].args[0].change).toBe("changed");
  });
  it("keeps unavailable baselines unmarked and marks entirely new CLIs", () => {
    expect(compareCommand(command(), null, "unavailable").count).toBe(0);
    const tree = compareCommand(command(), null, "added");
    expect(tree.change).toBe("added");
    expect(tree.args[0].change).toBe("added");
  });
});
