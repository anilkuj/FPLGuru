import { describe, expect, it, vi } from "vitest";

import { getOptimize } from "./api";

describe("optimize api", () => {
  it("getOptimize hits the optimize route with horizon + max_transfers", async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ entry_id: 7, current: { xi: [] }, transfer_plans: [], chips: [] }),
    });
    global.fetch = f as unknown as typeof fetch;

    await getOptimize("http://api.test", 7, 5, 2);
    expect(String(f.mock.calls[0][0])).toBe(
      "http://api.test/entries/7/optimize?horizon=5&max_transfers=2",
    );
  });

  it("getOptimize throws on !ok", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 }) as unknown as typeof fetch;
    await expect(getOptimize("http://api.test", 7)).rejects.toThrow();
  });
});
