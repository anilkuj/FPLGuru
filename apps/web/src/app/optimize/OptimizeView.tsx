"use client";

import { useEffect, useState } from "react";

import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Badge, Button, Card, Skeleton } from "@/components/ui";
import { getOptimize, type Optimize } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";
import { getPref, setPref } from "@/lib/prefs";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const HORIZONS = [1, 3, 5, 8];
const MAX_TRANSFERS = [0, 1, 2, 3];

const CHIP_LABEL: Record<string, string> = {
  bench_boost: "Bench Boost",
  triple_captain: "Triple Captain",
  free_hit: "Free Hit",
  wildcard: "Wildcard",
};

export function OptimizeView() {
  const [data, setData] = useState<Optimize | null>(null);
  const [state, setState] = useState<"loading" | "nolink" | "error" | "ok">("loading");
  const [horizon, setHorizon] = useState(() => getPref("optHorizon", 5));
  const [maxT, setMaxT] = useState(() => getPref("optMaxTransfers", 2));

  useEffect(() => {
    const id = getStoredEntryId();
    if (!id) {
      setState("nolink");
      return;
    }
    setState("loading");
    getOptimize(API, id, horizon, maxT)
      .then((d) => {
        setData(d);
        setState("ok");
      })
      .catch(() => setState("error"));
  }, [horizon, maxT]);

  if (state === "nolink")
    return (
      <>
        <PageHeader title="Optimize" />
        <EmptyState title="No team linked" hint="Link your FPL team ID on the home page." />
      </>
    );

  const rec = data?.transfer_plans?.[0];

  return (
    <>
      <PageHeader
        title="Optimize"
        description={
          data
            ? `${data.current.formation} · ${data.current.total.toFixed(1)} xP over ${data.horizon} GW · £${(data.bank / 10).toFixed(1)} in the bank`
            : undefined
        }
      />

      <div className="mb-3 flex flex-wrap items-center gap-4">
        <Segmented
          label="Horizon"
          value={horizon}
          options={HORIZONS}
          onPick={(v) => {
            setHorizon(v);
            setPref("optHorizon", v);
          }}
        />
        <Segmented
          label="Max transfers"
          value={maxT}
          options={MAX_TRANSFERS}
          onPick={(v) => {
            setMaxT(v);
            setPref("optMaxTransfers", v);
          }}
        />
      </div>

      {state === "error" && <p className="text-sm text-danger">Could not load the optimizer.</p>}
      {state === "loading" && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      )}

      {data && state === "ok" && (
        <div className="space-y-4">
          <Card className="p-4">
            <h2 className="mb-2 text-sm font-semibold">Recommended move</h2>
            {rec && rec.transfers.length > 0 ? (
              <div className="space-y-2">
                {rec.transfers.map((t, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <Badge variant="danger">OUT {t.out.web_name}</Badge>
                    <span className="text-fg-muted">→</span>
                    <Badge variant="positive">IN {t.in.web_name}</Badge>
                    <span className="text-fg-muted">
                      +{(t.in.xp - t.out.xp).toFixed(1)} xP
                    </span>
                  </div>
                ))}
                <div className="flex gap-2 pt-1 text-xs">
                  <Badge variant="outline">gain +{rec.gain.toFixed(1)}</Badge>
                  {rec.hit > 0 && <Badge variant="warning">hit −{rec.hit.toFixed(0)}</Badge>}
                  <Badge variant={rec.net >= 0 ? "positive" : "danger"}>
                    net {rec.net >= 0 ? "+" : ""}
                    {rec.net.toFixed(1)}
                  </Badge>
                </div>
              </div>
            ) : (
              <p className="text-sm text-fg-muted">
                No transfer beats a hit — roll your free transfer.
              </p>
            )}
          </Card>

          {data.chips.length > 0 && (
            <Card className="p-4">
              <h2 className="mb-2 text-sm font-semibold">Chip windows</h2>
              <div className="flex flex-wrap gap-1.5">
                {data.chips.map((c, i) => (
                  <Badge key={i} variant="primary" title={c.reason}>
                    {CHIP_LABEL[c.chip] ?? c.chip} · GW{c.gameweek_id}
                  </Badge>
                ))}
              </div>
            </Card>
          )}

          <Card className="p-1.5">
            <DataTable
              rows={data.current.xi}
              rowKey={(p) => p.player_id}
              emptyTitle="No XI"
              columns={[
                { key: "position", header: "Pos", className: "text-fg-muted" },
                { key: "web_name", header: "Player", className: "font-medium" },
                { key: "team_short", header: "Team", className: "text-fg-muted" },
                {
                  key: "xp",
                  header: "xP",
                  align: "right",
                  sortable: true,
                  render: (p) => p.xp.toFixed(1),
                  className: "font-semibold",
                },
                {
                  key: "role",
                  header: "",
                  render: (p) =>
                    data.current.captain?.player_id === p.player_id ? (
                      <Badge variant="primary">C</Badge>
                    ) : data.current.vice?.player_id === p.player_id ? (
                      <Badge>V</Badge>
                    ) : null,
                },
              ]}
            />
            <div className="mt-2 px-2 pb-1 text-xs text-fg-muted">
              Bench: {data.current.bench.map((p) => p.web_name).join(", ")}
            </div>
          </Card>
        </div>
      )}
    </>
  );
}

function Segmented({
  label,
  value,
  options,
  onPick,
}: {
  label: string;
  value: number;
  options: number[];
  onPick: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-fg-muted">{label}</span>
      <div className="inline-flex overflow-hidden rounded-md border border-border">
        {options.map((o) => (
          <Button
            key={o}
            size="sm"
            variant={value === o ? "default" : "ghost"}
            className="rounded-none border-0"
            onClick={() => onPick(o)}
          >
            {o}
          </Button>
        ))}
      </div>
    </div>
  );
}
