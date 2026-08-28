"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { RankLine } from "@/components/Chart";
import { Delta } from "@/components/Delta";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import { getEntryLeagues, getRankHistory, type MiniLeague, type RankPoint } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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
    return (
      <>
        <PageHeader title="Leagues" />
        <EmptyState title="Link your team first" hint="Your mini-leagues appear here once linked." />
      </>
    );

  return (
    <>
      <PageHeader
        title="Leagues"
        description="Your classic mini-leagues, weekly movement and overall-rank trend."
      />

      {rank.length >= 2 && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle>Overall rank trend</CardTitle>
          </CardHeader>
          <CardContent>
            <RankLine data={rank.map((r) => ({ gw: r.gameweek_id, rank: r.overall_rank }))} />
          </CardContent>
        </Card>
      )}

      {err && <p className="text-sm text-danger">{err}</p>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {leagues.map((l) => (
          <Link key={l.league_id} href={`/leagues/${l.league_id}`}>
            <Card className="h-full p-4 transition-colors hover:border-primary/40 hover:bg-surface-2">
              <p className="text-sm font-medium">{l.league_name}</p>
              <div className="mt-2 flex items-end justify-between">
                <span className="text-2xl font-semibold tabular-nums">
                  {l.entry_rank == null ? "—" : l.entry_rank.toLocaleString()}
                </span>
                <span className="text-sm">
                  <Delta value={l.delta} invert />
                </span>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}
