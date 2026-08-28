"use client";

import { useEffect, useState } from "react";

import { DataTable } from "@/components/DataTable";
import { Delta } from "@/components/Delta";
import { PageHeader } from "@/components/PageHeader";
import { Card, Input } from "@/components/ui";
import { getLeagueStandings, searchLeague, type StandingRow } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
type SearchHit = Pick<StandingRow, "entry_id" | "entry_name" | "player_name" | "rank" | "total">;

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
    const t = setTimeout(
      () => searchLeague(API, leagueId, q.trim()).then(setHits).catch(() => setHits([])),
      250,
    );
    return () => clearTimeout(t);
  }, [q, leagueId]);

  return (
    <>
      <PageHeader
        title="League standings"
        actions={
          <Input
            className="w-56"
            placeholder="Search manager or team…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        }
      />

      {hits.length > 0 && (
        <Card className="mb-3 p-3 text-sm">
          {hits.map((h) => (
            <div key={h.entry_id} className="text-fg-muted">
              #{h.rank.toLocaleString()} — {h.entry_name} ({h.player_name}) · {h.total} pts
            </div>
          ))}
        </Card>
      )}
      {err && <p className="text-sm text-danger">{err}</p>}

      <Card className="p-1.5">
        <DataTable
          rows={rows}
          rowKey={(r) => r.entry_id}
          initialSort={{ key: "rank", dir: "asc" }}
          emptyTitle="Standings not synced yet"
          emptyHint="The sync_league_standings task refreshes the top slice every 2 hours."
          columns={[
            { key: "rank", header: "#", align: "right", sortable: true, className: "tabular-nums" },
            {
              key: "delta",
              header: "Δ",
              render: (r) => <Delta value={r.delta} invert />,
            },
            { key: "player_name", header: "Manager" },
            { key: "entry_name", header: "Team", className: "font-medium" },
            { key: "event_total", header: "GW", align: "right", sortable: true },
            {
              key: "total",
              header: "Total",
              align: "right",
              sortable: true,
              className: "font-semibold",
            },
          ]}
        />
      </Card>
    </>
  );
}
