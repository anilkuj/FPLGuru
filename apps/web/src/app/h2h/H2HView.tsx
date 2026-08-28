"use client";

import { useState } from "react";

import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Badge, Button, Card, Input, Skeleton } from "@/components/ui";
import { getH2H, type H2H, type H2HPlayer } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";
import { getPrefStr, setPrefStr } from "@/lib/prefs";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const DIFF_COLUMNS = [
  { key: "web_name" as const, header: "Player", className: "font-medium" },
  { key: "position" as const, header: "Pos", className: "text-fg-muted" },
  {
    key: "xp" as const,
    header: "xP",
    align: "right" as const,
    sortable: true,
    render: (p: H2HPlayer) => p.xp.toFixed(1),
  },
];

export function H2HView() {
  const entryId = typeof window !== "undefined" ? getStoredEntryId() : null;
  const [opp, setOpp] = useState<string>(() => getPrefStr("h2hOpponent", ""));
  const [data, setData] = useState<H2H | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");

  if (!entryId)
    return (
      <>
        <PageHeader title="H2H" />
        <EmptyState title="No team linked" hint="Link your FPL team ID on the home page." />
      </>
    );

  function compare() {
    const id = Number(opp);
    if (!Number.isFinite(id) || id <= 0) return;
    setPrefStr("h2hOpponent", opp);
    setState("loading");
    getH2H(API, entryId as number, id)
      .then((d) => {
        setData(d);
        setState("idle");
      })
      .catch(() => setState("error"));
  }

  return (
    <>
      <PageHeader title="H2H Match Helper" description="Compare your squad to any manager's." />

      <div className="mb-4 flex items-end gap-2">
        <div>
          <label className="mb-1 block text-xs text-fg-muted">Opponent FPL team ID</label>
          <Input
            className="w-40"
            inputMode="numeric"
            value={opp}
            onChange={(e) => setOpp(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && compare()}
            placeholder="e.g. 123456"
          />
        </div>
        <Button onClick={compare} disabled={state === "loading"}>
          Compare
        </Button>
      </div>

      {state === "error" && (
        <p className="text-sm text-danger">
          Couldn&apos;t fetch that opponent — check the team ID.
        </p>
      )}
      {state === "loading" && (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      )}

      {data && state !== "loading" && (
        <div className="space-y-4">
          <Card className="p-4">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-2xl font-bold">
                <Badge variant={data.margin >= 0 ? "positive" : "danger"}>
                  {data.margin >= 0 ? "+" : ""}
                  {data.margin.toFixed(1)}
                </Badge>
              </span>
              <span className="text-sm text-fg-muted">
                you {data.your_xi_total.toFixed(1)} · {data.opponent_name}{" "}
                {data.their_xi_total.toFixed(1)} · next {data.horizon} GW · {data.model}
              </span>
            </div>
            <p className="mt-2 text-sm">{data.strategy}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="text-fg-muted">Captains:</span>
              <Badge variant={data.same_captain ? "warning" : "default"}>
                you · {data.your_captain?.web_name ?? "—"}
              </Badge>
              <Badge variant={data.same_captain ? "warning" : "default"}>
                them · {data.their_captain?.web_name ?? "—"}
              </Badge>
              <span className="text-fg-muted">{data.shared_count} players shared</span>
            </div>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2">
            <Card className="p-1.5">
              <div className="px-2 py-1.5 text-sm font-semibold">Your differentials</div>
              <DataTable
                rows={data.your_differentials}
                rowKey={(p) => p.player_id}
                initialSort={{ key: "xp", dir: "desc" }}
                emptyTitle="None — identical squads"
                columns={DIFF_COLUMNS}
              />
            </Card>
            <Card className="p-1.5">
              <div className="px-2 py-1.5 text-sm font-semibold">
                {data.opponent_name}&apos;s differentials
              </div>
              <DataTable
                rows={data.their_differentials}
                rowKey={(p) => p.player_id}
                initialSort={{ key: "xp", dir: "desc" }}
                emptyTitle="None — identical squads"
                columns={DIFF_COLUMNS}
              />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
