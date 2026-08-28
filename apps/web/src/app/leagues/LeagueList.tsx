"use client";

import { useEffect, useState } from "react";

import { getEntryLeagues, getRankHistory, type MiniLeague, type RankPoint } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";
import { RankSparkline } from "./RankSparkline";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function Delta({ d }: { d: number | null }) {
  if (d == null || d === 0) return <span className="text-gray-400">–</span>;
  return d > 0 ? (
    <span className="text-emerald-500">▲ {d.toLocaleString()}</span>
  ) : (
    <span className="text-red-500">▼ {Math.abs(d).toLocaleString()}</span>
  );
}

export function LeagueList() {
  const [entryId, setEntryId] = useState<number | null>(null);
  const [leagues, setLeagues] = useState<MiniLeague[]>([]);
  const [rank, setRank] = useState<RankPoint[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => setEntryId(getStoredEntryId()), []);

  useEffect(() => {
    if (entryId == null) return;
    getEntryLeagues(API, entryId).then(setLeagues).catch(() => setErr("Could not load leagues."));
    getRankHistory(API, entryId).then(setRank).catch(() => undefined);
  }, [entryId]);

  if (entryId == null)
    return <p className="mt-4 text-sm text-gray-500">Link your team first (Squad tab).</p>;

  return (
    <>
      {rank.length >= 2 && (
        <div className="mt-3">
          <p className="text-xs text-gray-500">Overall rank trend</p>
          <RankSparkline points={rank} />
        </div>
      )}
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      <table className="mt-4 text-sm border-collapse">
        <thead>
          <tr className="text-left">
            <th className="px-2 py-1">League</th>
            <th className="px-2 py-1 text-right">Rank</th>
            <th className="px-2 py-1 text-right">Weekly</th>
          </tr>
        </thead>
        <tbody>
          {leagues.map((l) => (
            <tr key={l.league_id} className="border-t">
              <td className="px-2 py-1">
                <a className="font-medium hover:underline" href={`/leagues/${l.league_id}`}>
                  {l.league_name}
                </a>
              </td>
              <td className="px-2 py-1 text-right">
                {l.entry_rank == null ? "—" : l.entry_rank.toLocaleString()}
              </td>
              <td className="px-2 py-1 text-right">
                <Delta d={l.delta} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
