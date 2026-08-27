import { describe, expect, it, vi } from "vitest";
import { fetchStatus } from "./api";

describe("fetchStatus", () => {
  it("returns the parsed status body", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ sources: { fpl_bootstrap: { status: "ok", as_of: "2025-08-20T12:00:00+00:00" } } }),
    }) as unknown as typeof fetch;

    const s = await fetchStatus("http://api.test");
    expect(s.sources.fpl_bootstrap.status).toBe("ok");
  });
});
