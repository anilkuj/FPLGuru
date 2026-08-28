import { describe, expect, it, vi } from "vitest";

import { createPlan, deletePlan, listPlans } from "./api";

describe("saved plans api", () => {
  it("listPlans GETs the plans route", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    global.fetch = f as unknown as typeof fetch;
    await listPlans("http://api.test", 7);
    expect(String(f.mock.calls[0][0])).toBe("http://api.test/entries/7/plans");
  });

  it("createPlan POSTs JSON", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 1 }) });
    global.fetch = f as unknown as typeof fetch;
    await createPlan("http://api.test", 7, { name: "x", horizon: 3, max_transfers: 1 });
    const [url, init] = f.mock.calls[0];
    expect(String(url)).toBe("http://api.test/entries/7/plans");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ name: "x", horizon: 3, max_transfers: 1 });
  });

  it("deletePlan issues DELETE and throws on !ok", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 }) as unknown as typeof fetch;
    await expect(deletePlan("http://api.test", 7, 9)).rejects.toThrow();
  });
});
