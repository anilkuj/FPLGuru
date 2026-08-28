import { describe, expect, it, vi } from "vitest";

import { getH2H } from "./api";

describe("h2h api", () => {
  it("getH2H hits the h2h route with the opponent id + horizon", async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ opponent_entry_id: 42, your_differentials: [], their_differentials: [] }),
    });
    global.fetch = f as unknown as typeof fetch;

    await getH2H("http://api.test", 7, 42, 5);
    expect(String(f.mock.calls[0][0])).toBe("http://api.test/entries/7/h2h/42?horizon=5");
  });

  it("getH2H throws on !ok", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 502 }) as unknown as typeof fetch;
    await expect(getH2H("http://api.test", 7, 42)).rejects.toThrow();
  });
});
