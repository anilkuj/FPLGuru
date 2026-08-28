import { describe, expect, it, vi } from "vitest";

import { getCalendar, getOverpowered, getTemplate, getTrends } from "./api";

const ok = (j: unknown) => ({ ok: true, json: async () => j });

describe("tools api", () => {
  it("getTrends", async () => {
    const f = vi.fn().mockResolvedValue(ok({ transfers_in: [] }));
    global.fetch = f as unknown as typeof fetch;
    await getTrends("http://api.test");
    expect(String(f.mock.calls[0][0])).toContain("/trends");
  });

  it("getCalendar passes range", async () => {
    const f = vi.fn().mockResolvedValue(ok([]));
    global.fetch = f as unknown as typeof fetch;
    await getCalendar("http://api.test", 5, 10);
    expect(String(f.mock.calls[0][0])).toContain("from_gw=5");
    expect(String(f.mock.calls[0][0])).toContain("to_gw=10");
  });

  it("getOverpowered + getTemplate", async () => {
    const f = vi.fn().mockResolvedValue(ok({ xi: [] }));
    global.fetch = f as unknown as typeof fetch;
    await getOverpowered("http://api.test", 5);
    await getTemplate("http://api.test");
    expect(String(f.mock.calls[0][0])).toContain("/overpowered?horizon=5");
    expect(String(f.mock.calls[1][0])).toContain("/template");
  });
});
