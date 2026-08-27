import { describe, expect, it, vi } from "vitest";

import { getLive } from "./api";

describe("getLive", () => {
  it("fetches the current-GW live snapshot", async () => {
    const snap = {
      gameweek_id: 3,
      updated_at: "2026-08-27T14:00:00+00:00",
      fixtures: [],
      players: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snap });
    global.fetch = fetchMock as unknown as typeof fetch;

    const r = await getLive("http://api.test");
    expect(r.gameweek_id).toBe(3);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/gameweeks/current/live");
  });
});
