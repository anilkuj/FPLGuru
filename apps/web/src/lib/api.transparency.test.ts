import { describe, expect, it, vi } from "vitest";

import { getTransparency } from "./api";

describe("transparency api", () => {
  it("getTransparency hits the model route with last=", async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ models: [], by_position: {}, rolling: {}, last_gw: null }),
    });
    global.fetch = f as unknown as typeof fetch;

    await getTransparency("http://api.test", 6);
    expect(String(f.mock.calls[0][0])).toBe("http://api.test/model/transparency?last=6");
  });

  it("getTransparency throws on !ok", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 }) as unknown as typeof fetch;
    await expect(getTransparency("http://api.test")).rejects.toThrow();
  });
});
