import { expect, it } from "vite-plus/test";
import { parseSession } from "./sessions";

it("rejects foreign or malformed page session responses", () => {
  const preview = "a".repeat(32),
    revision = "b".repeat(40);
  const binding = {
    id: "00000000-0000-4000-8000-000000000001",
    preview_id: preview,
    revision,
    credential: "c".repeat(43),
    absolute_deadline: "2099-01-01T01:00:00Z",
    state: "ready",
    reason: null,
  };
  expect(parseSession(binding, preview, revision)).toEqual(binding);
  for (const change of [
    { preview_id: "d".repeat(32) },
    { revision: "e".repeat(40) },
    { credential: "short" },
    { state: "unknown" },
    { absolute_deadline: "tomorrow" },
    { token: "extra" },
  ]) {
    expect(() => parseSession({ ...binding, ...change }, preview, revision)).toThrow();
  }
});
