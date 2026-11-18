import { z } from "zod";

const sessionSchema = z.strictObject({
  id: z.uuid(),
  preview_id: z.string().regex(/^[a-f0-9]{32}$/),
  revision: z.string().regex(/^[a-f0-9]{40}(?:-[1-9][0-9]*-[1-9][0-9]*)?$/),
  credential: z.string().regex(/^[A-Za-z0-9_-]{43}$/),
  absolute_deadline: z.iso.datetime({ offset: true }),
  state: z.enum(["accepted", "provisioning", "ready", "terminating", "terminated", "failed"]),
  reason: z.string().nullable(),
});
export type SessionBinding = z.infer<typeof sessionSchema>;

export function parseSession(value: unknown, preview: string, revision: string): SessionBinding {
  const parsed = sessionSchema.parse(value);
  if (parsed.preview_id !== preview || parsed.revision !== revision)
    throw new Error("Session binding does not match the requested preview and revision");
  return parsed;
}

export async function createFreshBinding(
  preview: string,
  revision: string,
): Promise<SessionBinding> {
  const response = await fetch(`/api/environments/${encodeURIComponent(preview)}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ revision }),
    cache: "no-store",
  });
  if (!response.ok) throw new Error("Session admission failed");
  return parseSession(await response.json(), preview, revision);
}

export async function stopBinding(binding: SessionBinding): Promise<void> {
  await fetch(`/api/environments/${binding.preview_id}/sessions/${binding.id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${binding.credential}` },
    keepalive: true,
  });
}
