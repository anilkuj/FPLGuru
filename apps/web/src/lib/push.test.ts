import { describe, expect, it, vi } from "vitest";

import { getVapidKey, urlBase64ToUint8Array } from "./push";

describe("push lib", () => {
  it("getVapidKey reads the endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ key: "abc" }) });
    global.fetch = fetchMock as unknown as typeof fetch;
    expect(await getVapidKey("http://api.test")).toBe("abc");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/push/vapid-public-key");
  });

  it("urlBase64ToUint8Array decodes standard web-push keys", () => {
    const out = urlBase64ToUint8Array("AAECAw"); // 0,1,2,3
    expect(Array.from(out)).toEqual([0, 1, 2, 3]);
  });
});
