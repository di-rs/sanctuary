import { describe, expect, test } from "vite-plus/test";
import { commandContext, tokens } from "./command-context";
import { indexCatalog } from "./catalog-diff";
import { argument, catalog, command } from "../../testing/catalog";
const reference = catalog("a".repeat(40), ["biggie", "echor"]);
reference.clis[0].head.command.subcommands = [
  command({
    name: "text",
    aliases: ["txt"],
    about: "Generate text",
    args: [
      argument({
        id: "lines",
        long: "lines",
        short: "n",
        num_args: { min: 1, max: 1 },
        value_names: ["LINES"],
      }),
    ],
  }),
  command({ name: "bytes" }),
  command({ name: "records" }),
];
const commands = indexCatalog(reference);
const context = (text: string) => commandContext(text, ["biggie", "echor"], commands);
describe("terminal-driven command choices", () => {
  test("starts with CLI buttons and completes names without artifact paths", () => {
    expect(context("").choices.map((choice) => choice.label)).toEqual(["biggie", "echor"]);
    expect(context("big").choices[0].value).toBe("biggie ");
  });
  test("filters subcommands by a substring and completes only the partial token", () => {
    expect(context("biggie").choices.map((choice) => choice.label)).toEqual([
      "text",
      "bytes",
      "records",
    ]);
    const partial = context("biggie t");
    expect(partial.query).toBe("t");
    expect(partial.choices.map((choice) => choice.label)).toEqual(["text", "bytes"]);
    expect(partial.choices[0].value).toBe("biggie text ");
    expect(context("biggie xyz").kind).toBe("missing");
    expect(context("biggie xyz another").kind).toBe("missing");
  });
  test("exact commands and aliases show their own flags", () => {
    expect(context("biggie text").node?.path).toEqual(["text"]);
    expect(context("biggie txt").flags[0].argument.long).toBe("lines");
    expect(context("biggie text --li").choices[0].value).toBe("biggie text --lines ");
    expect(context("biggie text --unknown").kind).toBe("missing");
  });
  test("flag values do not become commands and already used flags are tracked", () => {
    expect(context("biggie text --lines").kind).toBe("value");
    expect(context("biggie text --lines 12").used).toEqual(["lines"]);
    expect(context("biggie text --lines=12").used).toEqual(["lines"]);
  });
  test("does not guess for complex shells or incomplete quotes", () => {
    for (const value of [
      "biggie | cat",
      "biggie;echo hi",
      "biggie $(whoami)",
      "biggie 'unfinished",
    ])
      expect(context(value).kind).toBe("unsupported");
    expect(tokens("echor 'hello world'")?.map((token) => token.value)).toEqual([
      "echor",
      "hello world",
    ]);
  });
});

test("end-of-options stops flag and command suggestions", () => {
  for (const text of ["biggie text --", "biggie text '--'", "biggie --"]) {
    const result = context(text);
    expect(result.endOfOptions).toBe(true);
    expect(result.flags).toEqual([]);
    expect(result.choices).toEqual([]);
  }
  const withOperand = catalog("a".repeat(40), ["echor"]);
  withOperand.clis[0].head.command.args.push(
    argument({ id: "text", short: null, long: null, index: 1 }),
  );
  expect(commandContext("echor -- hello", ["echor"], indexCatalog(withOperand)).flags).toEqual([]);
  expect(context("biggie text --lines --").endOfOptions).toBe(false);
  expect(context("biggie text --lines=--").flags.length).toBeGreaterThan(0);
});

test("flags after operands still request values and track used options", () => {
  const reference = catalog("a".repeat(40), ["headr"]);
  reference.clis[0].head.command.args.push(
    argument({ id: "file", short: null, long: null, index: 1 }),
    argument({ id: "lines", short: "n", long: "lines", num_args: { min: 1, max: 1 } }),
  );
  const commands = indexCatalog(reference);
  const parse = (text: string) => commandContext(text, ["headr"], commands);
  expect(parse("headr welcome.txt --lines").kind).toBe("value");
  expect(parse("headr welcome.txt --lines").pending?.argument.id).toBe("lines");
  expect(parse("headr welcome.txt --lines 5").used).toEqual(["lines"]);
  expect(parse("headr welcome.txt --lines=5").used).toEqual(["lines"]);
  expect(parse("headr welcome.txt --li").choices[0].value).toBe("headr welcome.txt --lines ");
  expect(parse("headr -- welcome.txt --lines 5").used).toEqual([]);
});
