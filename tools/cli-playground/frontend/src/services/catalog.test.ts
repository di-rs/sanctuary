import { expect, it } from "vite-plus/test";
import { catalog } from "../../testing/catalog";
import { parseCatalog } from "./catalog";

it("ties the catalog to the exact active head and CLI set", () => {
  const value = catalog("a".repeat(40));
  expect(parseCatalog(value, value.head_sha, ["catr"])).toEqual(value);
  expect(() => parseCatalog(value, "b".repeat(40), ["catr"])).toThrow();
  expect(() => parseCatalog(value, value.head_sha, ["echor"])).toThrow();
  expect(() => parseCatalog({ ...value, schema_version: 2 }, value.head_sha, ["catr"])).toThrow();
});
