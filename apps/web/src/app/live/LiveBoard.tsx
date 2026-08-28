"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Badge, Button, Card, Skeleton } from "@/components/ui";
import { getEntry, getLive, type LiveSnapshot } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function LiveBoard() {
  const [snap, setSnap] = useState<LiveSnapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mineOnly, setMineOnly] = useState(false);
  const [squad, setSquad] = useState<Set<number> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const id = getStoredEntryId();
    if (id == null) return;
    getEntry(API, id)
      .then((e) => setSquad(new Set(e.picks.map((p) => p.player_id))))
      .catch(() => setSquad(null));
  }, []);

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
          /* keepalive */
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

  return (
    <>
      <PageHeader
        title="GW Live"
        description="Live points and a BPS-based bonus projection, updating during matches."
        actions={
          <div className="flex items-center gap-2 text-sm text-fg-muted">
            {snap?.updated_at ? (
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 animate-pulse rounded-full bg-positive" />
                {new Date(snap.updated_at).toLocaleTimeString()}
              </span>
            ) : (
              <span>no live data yet</span>
            )}
            {squad && (
              <Button
                size="sm"
                variant={mineOnly ? "default" : "outline"}
                onClick={() => setMineOnly((v) => !v)}
              >
                My players
              </Button>
            )}
          </div>
        }
      />

      {err && <p className="text-sm text-warning">{err}</p>}

      {!snap && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      )}

      {snap && snap.gameweek_id == null && (
        <EmptyState title="No active gameweek" hint="Live scores appear once a gameweek is underway." />
      )}

      {snap && snap.gameweek_id != null && (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {snap.fixtures.map((f) => (
              <Card key={f.id} className="px-2.5 py-1.5 text-sm">
                <span className="tabular-nums">
                  {f.home_team_id} {f.started ? (f.home_score ?? 0) : "–"} :{" "}
                  {f.started ? (f.away_score ?? 0) : "–"} {f.away_team_id}
                </span>
                <span className="ml-2 text-xs text-fg-muted">
                  {f.finished ? "FT" : f.started ? `${f.minutes}'` : ""}
                </span>
              </Card>
            ))}
          </div>

          <Card className="p-1.5">
            <DataTable
              rows={players}
              rowKey={(p) => p.player_id}
              initialSort={{ key: "total_points", dir: "desc" }}
              emptyTitle="No featured players yet"
              columns={[
                { key: "web_name", header: "Player", className: "font-medium" },
                { key: "position", header: "Pos", className: "text-fg-muted" },
                { key: "minutes", header: "Min", align: "right", sortable: true },
                { key: "live_points", header: "Pts", align: "right", sortable: true },
                {
                  key: "projected_bonus",
                  header: "Bonus",
                  align: "right",
                  render: (p) =>
                    p.projected_bonus ? (
                      <Badge variant="primary">+{p.projected_bonus}</Badge>
                    ) : (
                      <span className="text-fg-muted">—</span>
                    ),
                },
                { key: "bps", header: "BPS", align: "right", sortable: true, className: "text-fg-muted" },
                {
                  key: "total_points",
                  header: "Total",
                  align: "right",
                  sortable: true,
                  className: "font-semibold",
                },
              ]}
            />
          </Card>
          <p className="mt-2 text-xs text-fg-muted">
            Bonus is a live BPS projection and can change until fixtures are final.
          </p>
        </>
      )}
    </>
  );
}
