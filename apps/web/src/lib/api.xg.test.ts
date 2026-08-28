import { describe, expect, it, vi } from "vitest";

import { getXgSnapshot } from "./api";

describe("getXgSnapshot", () => {
  it("passes last + position", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ players: [] }) });
    global.fetch = f as unknown as typeof fetch;
    await getXgSnapshot("http://api.test", 6, "MID");
    expect(String(f.mock.calls[0][0])).toContain("last=6");
    expect(String(f.mock.calls[0][0])).toContain("position=MID");
  });
});
