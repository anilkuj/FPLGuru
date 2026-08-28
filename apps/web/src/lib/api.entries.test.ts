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

  it("getEntry passes ?model= only when not auto", async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ fpl_entry_id: 7, picks: [] }),
    });
    global.fetch = f as unknown as typeof fetch;

    await getEntry("http://api.test", 7);
    expect(String(f.mock.calls[0][0])).toBe("http://api.test/entries/7");

    await getEntry("http://api.test", 7, "basic");
    expect(String(f.mock.calls[1][0])).toBe("http://api.test/entries/7?model=basic");
  });
});
