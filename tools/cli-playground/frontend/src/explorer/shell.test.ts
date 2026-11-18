import { expect, it } from "vite-plus/test";
import { argument } from "../../testing/catalog";
import { commandText, flagText, quoteToken } from "./shell";

it("quotes tokens and never inserts Enter or positional placeholders", () => {
  expect(commandText("catr", ["run", "a'b;$HOME"])).toBe(`catr run 'a'"'"'b;$HOME' `);
  expect(
    flagText(argument({ long: "file", num_args: { min: 1, max: 1 }, value_names: ["FILE"] })),
  ).toBe(" --file ");
  expect(flagText(argument({ long: null, short: "n" }))).toBe(" -n ");
  expect(flagText(argument({ long: null, short: null, index: 1 }))).toBe("");
  for (const token of [
    "",
    "evil\ncommand",
    "evil\rcommand",
    "evil\x1b[200~",
    "evil\u009b",
    "evil\u2028",
  ])
    expect(() => quoteToken(token)).toThrow();
});
