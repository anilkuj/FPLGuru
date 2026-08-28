import { describe, expect, it, vi } from "vitest";

import {
  getAlerts,
  getEntrySettings,
  markAlertsSeen,
  updateEntrySettings,
} from "./api";

describe("alerts api", () => {
  it("getAlerts hits the feed endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ alerts: [], unseen: 0 }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    const r = await getAlerts("http://api.test", 7);
    expect(r.unseen).toBe(0);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/entries/7/alerts");
  });

  it("markAlertsSeen posts ids", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ marked: 1 }) });
    global.fetch = fetchMock as unknown as typeof fetch;
    await markAlertsSeen("http://api.test", 7, [3]);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ ids: [3] });
  });
});

describe("entry settings api", () => {
  it("getEntrySettings reads current values", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ alert_cap: null, reminder_offsets: [120, 30] }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    const r = await getEntrySettings("http://api.test", 7);
    expect(r.reminder_offsets).toEqual([120, 30]);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/entries/7/settings");
  });

  it("updateEntrySettings sends both fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ alert_cap: 5, reminder_offsets: [60] }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    await updateEntrySettings("http://api.test", 7, { alertCap: 5, reminderOffsets: [60] });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ alert_cap: 5, reminder_offsets: [60] });
  });
});
