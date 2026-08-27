import { describe, expect, it, vi } from "vitest";
import { getEntry, linkEntry } from "./api";

describe("entries api", () => {
  it("linkEntry POSTs and returns body", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ fpl_entry_id: 7, manager_name: "Sam Q" }),
    }) as unknown as typeof fetch;
    const r = await linkEntry("http://api.test", 7);
    expect(r.fpl_entry_id).toBe(7);
  });

  it("getEntry throws on !ok", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 }) as unknown as typeof fetch;
    await expect(getEntry("http://api.test", 7)).rejects.toThrow();
  });
});
