"use client";

import { useCallback, useEffect, useState } from "react";

import { type Alert, getAlerts, markAlertsSeen, updateEntrySettings } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const TONE: Record<string, string> = {
  availability: "border-red-300",
  bgw: "border-amber-300",
  dgw: "border-emerald-300",
};

export function AlertFeed() {
  const [entryId, setEntryId] = useState<number | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cap, setCap] = useState<string>("");
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

  if (entryId == null)
    return <p className="mt-4 text-sm text-gray-500">Link your team first (Squad tab).</p>;

  return (
    <>
      <div className="mt-2 flex items-center gap-3 text-sm">
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
            onClick={() =>
              updateEntrySettings(API, entryId, cap === "" ? null : Number(cap)).then(load)
            }
          >
            Save
          </button>
        </label>
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
