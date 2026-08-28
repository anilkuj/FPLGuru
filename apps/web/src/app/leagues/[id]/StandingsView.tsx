"use client";

import { useEffect, useState } from "react";

import { getLeagueStandings, searchLeague, type StandingRow } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

type SearchHit = Pick<StandingRow, "entry_id" | "entry_name" | "player_name" | "rank" | "total">;

function Delta({ d }: { d: number | null }) {
  if (d == null || d === 0) return <span className="text-gray-400">–</span>;
  return d > 0 ? (
    <span className="text-emerald-500">▲{d}</span>
  ) : (
    <span className="text-red-500">▼{Math.abs(d)}</span>
  );
}

export function StandingsView({ leagueId }: { leagueId: number }) {
  const [rows, setRows] = useState<StandingRow[]>([]);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getLeagueStandings(API, leagueId)
      .then((d) => setRows(d.standings))
      .catch(() => setErr("Could not load standings."));
  }, [leagueId]);

  useEffect(() => {
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const t = setTimeout(() => {
      searchLeague(API, leagueId, q.trim()).then(setHits).catch(() => setHits([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q, leagueId]);

  return (
    <>
      <input
        className="mt-3 w-64 rounded border px-2 py-1 text-sm"
        placeholder="Search manager or team…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {hits.length > 0 && (
        <ul className="mt-2 text-sm">
          {hits.map((h) => (
            <li key={h.entry_id} className="text-gray-600">
              #{h.rank.toLocaleString()} — {h.entry_name} ({h.player_name}) · {h.total} pts
            </li>
          ))}
        </ul>
      )}
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      <div className="mt-4 overflow-x-auto">
        <table className="text-sm border-collapse">
          <thead>
            <tr className="text-left">
              <th className="px-2 py-1 text-right">#</th>
              <th className="px-2 py-1">Δ</th>
              <th className="px-2 py-1">Manager</th>
              <th className="px-2 py-1">Team</th>
              <th className="px-2 py-1 text-right">GW</th>
              <th className="px-2 py-1 text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.entry_id} className="border-t">
                <td className="px-2 py-1 text-right">{r.rank.toLocaleString()}</td>
                <td className="px-2 py-1">
                  <Delta d={r.delta} />
                </td>
                <td className="px-2 py-1">{r.player_name}</td>
                <td className="px-2 py-1 font-medium">{r.entry_name}</td>
                <td className="px-2 py-1 text-right">{r.event_total}</td>
                <td className="px-2 py-1 text-right font-semibold">{r.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length === 0 && !err && (
        <p className="mt-3 text-sm text-gray-500">
          Standings not synced yet — check back after the next refresh.
        </p>
      )}
    </>
  );
}
