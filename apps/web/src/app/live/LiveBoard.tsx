"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getEntry, getLive, type LiveSnapshot } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function LiveBoard() {
  const [snap, setSnap] = useState<LiveSnapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mineOnly, setMineOnly] = useState(false);
  const [squad, setSquad] = useState<Set<number> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // one-time: my squad (for the "my players" filter)
  useEffect(() => {
    const id = getStoredEntryId();
    if (id == null) return;
    getEntry(API, id)
      .then((e) => setSquad(new Set(e.picks.map((p) => p.player_id))))
      .catch(() => setSquad(null));
  }, []);

  // live data: SSE, with a polling fallback if the stream errors
  useEffect(() => {
    let closed = false;
    getLive(API).then(setSnap).catch(() => undefined);

    const startPolling = () => {
      if (pollRef.current) return;
      pollRef.current = setInterval(() => {
        getLive(API)
          .then((s) => {
            setSnap(s);
            setErr(null);
          })
          .catch(() => setErr("Live updates unavailable — retrying."));
      }, 15000);
    };

    let es: EventSource | null = null;
    try {
      es = new EventSource(`${API}/gameweeks/current/live/stream`);
      es.onmessage = (ev) => {
        if (closed) return;
        try {
          setSnap(JSON.parse(ev.data) as LiveSnapshot);
          setErr(null);
        } catch {
          /* ignore keepalive / partial */
        }
      };
      es.onerror = () => {
        es?.close();
        startPolling();
      };
    } catch {
      startPolling();
    }

    return () => {
      closed = true;
      es?.close();
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, []);

  const players = useMemo(() => {
    const all = snap?.players ?? [];
    return mineOnly && squad ? all.filter((p) => squad.has(p.player_id)) : all;
  }, [snap, mineOnly, squad]);

  if (!snap) return <p className="mt-4 text-sm text-gray-500">Loading…</p>;
  if (snap.gameweek_id == null)
    return <p className="mt-4 text-sm text-gray-500">No active gameweek.</p>;

  return (
    <>
      <div className="mt-2 flex items-center gap-3 text-sm text-gray-500">
        <span>
          GW{snap.gameweek_id}
          {snap.updated_at
            ? ` · updated ${new Date(snap.updated_at).toLocaleTimeString()}`
            : " · no live data yet"}
        </span>
        {squad && (
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={mineOnly}
              onChange={(e) => setMineOnly(e.target.checked)}
            />
            My players
          </label>
        )}
      </div>
      {err && <p className="mt-2 text-sm text-amber-600">{err}</p>}

      <div className="mt-4 flex flex-wrap gap-2">
        {snap.fixtures.map((f) => (
          <span key={f.id} className="rounded border px-2 py-1 text-sm">
            {f.home_team_id}&nbsp;
            {f.started ? (f.home_score ?? 0) : "–"}
            {" - "}
            {f.started ? (f.away_score ?? 0) : "–"}&nbsp;{f.away_team_id}
            <span className="ml-1 text-gray-400">
              {f.finished ? "FT" : f.started ? `${f.minutes}'` : ""}
            </span>
          </span>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="text-sm border-collapse">
          <thead>
            <tr className="text-left">
              <th className="px-2 py-1">Player</th>
              <th className="px-2 py-1">Pos</th>
              <th className="px-2 py-1 text-right">Min</th>
              <th className="px-2 py-1 text-right">Pts</th>
              <th className="px-2 py-1 text-right">Bonus*</th>
              <th className="px-2 py-1 text-right">BPS</th>
              <th className="px-2 py-1 text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.player_id} className="border-t">
                <td className="px-2 py-1 font-medium">{p.web_name}</td>
                <td className="px-2 py-1 text-gray-500">{p.position}</td>
                <td className="px-2 py-1 text-right">{p.minutes}</td>
                <td className="px-2 py-1 text-right">{p.live_points}</td>
                <td className="px-2 py-1 text-right text-gray-500">
                  {p.projected_bonus ? `+${p.projected_bonus}` : "—"}
                </td>
                <td className="px-2 py-1 text-right text-gray-400">{p.bps}</td>
                <td className="px-2 py-1 text-right font-semibold">{p.total_points}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-gray-400">
        *Bonus is a live BPS projection and can change until fixtures are final.
      </p>
    </>
  );
}
