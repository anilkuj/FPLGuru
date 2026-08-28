import { describe, expect, it, vi } from "vitest";

import { getEntryLeagues, getLeagueStandings, getRankHistory } from "./api";

const ok = (json: unknown) => ({ ok: true, json: async () => json });

describe("leagues api", () => {
  it("getEntryLeagues", async () => {
    const f = vi.fn().mockResolvedValue(ok([{ league_id: 1, delta: 2 }]));
    global.fetch = f as unknown as typeof fetch;
    const r = await getEntryLeagues("http://api.test", 7);
    expect(r[0].delta).toBe(2);
    expect(String(f.mock.calls[0][0])).toContain("/entries/7/leagues");
  });

  it("getLeagueStandings", async () => {
    const f = vi.fn().mockResolvedValue(ok({ league_id: 1, standings: [] }));
    global.fetch = f as unknown as typeof fetch;
    await getLeagueStandings("http://api.test", 1);
    expect(String(f.mock.calls[0][0])).toContain("/leagues/1/standings");
  });

  it("getRankHistory", async () => {
    const f = vi.fn().mockResolvedValue(ok([{ gameweek_id: 1, overall_rank: 10 }]));
    global.fetch = f as unknown as typeof fetch;
    const r = await getRankHistory("http://api.test", 7);
    expect(r[0].overall_rank).toBe(10);
  });
});
