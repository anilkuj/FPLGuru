import { describe, expect, it, vi } from "vitest";

import { getCaptain } from "./api";

describe("getCaptain", () => {
  it("passes entry id and horizon", async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ constrained: [], unconstrained: [], rationale: {} }),
    });
    global.fetch = f as unknown as typeof fetch;
    await getCaptain("http://api.test", 7, 3);
    expect(String(f.mock.calls[0][0])).toContain("/entries/7/captain?horizon=3");
  });
});
