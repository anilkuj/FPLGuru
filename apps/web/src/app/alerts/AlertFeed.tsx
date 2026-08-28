"use client";

import { useCallback, useEffect, useState } from "react";

import {
  type Alert,
  getAlerts,
  getEntrySettings,
  markAlertsSeen,
  updateEntrySettings,
} from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const TONE: Record<string, string> = {
  availability: "border-red-300",
  bgw: "border-amber-300",
  dgw: "border-emerald-300",
  deadline: "border-sky-300",
};
const PRESETS = [1440, 120, 60, 30];
const PRESET_LABEL: Record<number, string> = { 1440: "24h", 120: "2h", 60: "1h", 30: "30m" };

export function AlertFeed() {
  const [entryId, setEntryId] = useState<number | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cap, setCap] = useState<string>("");
  const [offsets, setOffsets] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => setEntryId(getStoredEntryId()), []);

  const load = useCallback(() => {
    if (entryId == null) return;
    getAlerts(API, entryId)
      .then((f) => {
        setAlerts(f.alerts);
        setErr(null);
      })
      .catch(() => setErr("Could not load alerts."));
  }, [entryId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (entryId == null) return;
    getEntrySettings(API, entryId)
      .then((s) => {
        setCap(s.alert_cap == null ? "" : String(s.alert_cap));
        setOffsets(s.reminder_offsets.join(", "));
      })
      .catch(() => undefined);
  }, [entryId]);

  const parseOffsets = (text: string) =>
    text
      .split(",")
      .map((s) => Number(s.trim()))
      .filter((n) => Number.isFinite(n) && n > 0);

  const saveSettings = (nextOffsets: number[]) => {
    if (entryId == null) return;
    updateEntrySettings(API, entryId, {
      alertCap: cap === "" ? null : Number(cap),
      reminderOffsets: nextOffsets,
    })
      .then((s) => setOffsets(s.reminder_offsets.join(", ")))
      .then(load)
      .catch(() => setErr("Could not save settings."));
  };

  const togglePreset = (m: number) => {
    const cur = new Set(parseOffsets(offsets));
    if (cur.has(m)) cur.delete(m);
    else cur.add(m);
    saveSettings([...cur].sort((a, b) => b - a));
  };

  if (entryId == null)
    return <p className="mt-4 text-sm text-gray-500">Link your team first (Squad tab).</p>;

  const active = new Set(parseOffsets(offsets));

  return (
    <>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
        <button
          className="rounded border px-2 py-1"
          onClick={() => markAlertsSeen(API, entryId).then(load)}
        >
          Mark all read
        </button>
        <label className="flex items-center gap-1 text-gray-500">
          Max alerts
          <input
            className="w-16 rounded border px-1 py-0.5"
            value={cap}
            onChange={(e) => setCap(e.target.value.replace(/[^0-9]/g, ""))}
            placeholder="∞"
          />
          <button
            className="rounded border px-2 py-0.5"
            onClick={() => saveSettings(parseOffsets(offsets))}
          >
            Save
          </button>
        </label>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-gray-500">
        Deadline reminders
        {PRESETS.map((m) => (
          <button
            key={m}
            className={`rounded border px-2 py-0.5 ${
              active.has(m) ? "bg-sky-200 border-sky-300" : ""
            }`}
            onClick={() => togglePreset(m)}
          >
            {PRESET_LABEL[m]}
          </button>
        ))}
        <input
          className="w-40 rounded border px-1 py-0.5"
          value={offsets}
          onChange={(e) => setOffsets(e.target.value)}
          placeholder="minutes, comma-separated"
        />
        <button
          className="rounded border px-2 py-0.5"
          onClick={() => saveSettings(parseOffsets(offsets))}
        >
          Save
        </button>
      </div>

      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      <ul className="mt-4 space-y-2">
        {alerts.length === 0 && (
          <li className="text-sm text-gray-500">No alerts right now.</li>
        )}
        {alerts.map((a) => (
          <li
            key={a.id}
            className={`rounded border-l-4 bg-white/5 px-3 py-2 ${TONE[a.type] ?? "border-gray-300"} ${
              a.seen ? "opacity-60" : ""
            }`}
          >
            <div className="flex justify-between text-sm font-medium">
              <span>{a.title}</span>
              <span className="text-gray-400">p{a.priority}</span>
            </div>
            <p className="text-sm text-gray-500">{a.body}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
