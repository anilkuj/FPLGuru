import { describe, expect, it, vi } from "vitest";

import { getXpExplain } from "./api";

describe("xp explain api", () => {
  it("getXpExplain hits the explain route with horizon + model", async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ player_id: 11, drivers: [], text: "x", source: "template" }),
    });
    global.fetch = f as unknown as typeof fetch;

    await getXpExplain("http://api.test", 11, 3);
    expect(String(f.mock.calls[0][0])).toBe(
      "http://api.test/players/11/xp/explain?horizon=3&model=advanced",
    );
  });

  it("getXpExplain throws on !ok", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 }) as unknown as typeof fetch;
    await expect(getXpExplain("http://api.test", 999)).rejects.toThrow();
  });
});
