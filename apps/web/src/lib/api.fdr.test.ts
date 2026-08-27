import { describe, expect, it, vi } from "vitest";
import { getFdr } from "./api";

describe("getFdr", () => {
  it("passes horizon and returns the grid", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ start_gw: 4, horizon: 5, teams: [] }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    const r = await getFdr("http://api.test", 5);
    expect(r.start_gw).toBe(4);
    expect(String(fetchMock.mock.calls[0][0])).toContain("horizon=5");
  });
});
