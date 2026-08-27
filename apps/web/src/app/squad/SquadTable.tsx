"use client";

import { useEffect, useState } from "react";

import { type Entry, getEntry } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function SquadTable() {
  const [entry, setEntry] = useState<Entry | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const id = getStoredEntryId();
    if (!id) {
      setErr("No team linked yet — go to the home page.");
      return;
    }
    getEntry(API, id)
      .then(setEntry)
      .catch(() => setErr("Could not load squad."));
  }, []);

  if (err) return <p className="mt-4 text-sm text-gray-500">{err}</p>;
  if (!entry) return <p className="mt-4 text-sm text-gray-400">Loading…</p>;

  return (
    <>
      <p className="mt-1 text-sm text-gray-500">
        {entry.manager_name} · picks from GW {entry.picks_gameweek_id ?? "—"}
      </p>
      <table className="mt-4 w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th className="py-1">Player</th>
            <th>Pos</th>
            <th className="text-right">£</th>
            <th className="text-right">xP (5)</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {entry.picks.map((p) => (
            <tr key={p.player_id} className="border-b">
              <td className="py-1">{p.web_name}</td>
              <td>{p.position}</td>
              <td className="text-right">{(p.now_cost / 10).toFixed(1)}</td>
              <td className="text-right">{p.xp.toFixed(1)}</td>
              <td>{p.is_captain ? "C" : p.is_vice ? "V" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
