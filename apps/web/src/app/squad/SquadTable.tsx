"use client";

import { useCallback, useEffect, useState } from "react";

import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Badge, Button, Card, Skeleton } from "@/components/ui";
import { type Entry, getEntry, type XpModel } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";
import { getPrefStr, setPrefStr } from "@/lib/prefs";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const MODEL_LABEL: Record<string, string> = {
  "adv-v1": "Advanced",
  "basic-v1": "Basic",
};

export function SquadTable() {
  const [entry, setEntry] = useState<Entry | null>(null);
  const [state, setState] = useState<"loading" | "nolink" | "error" | "ok">("loading");
  const [model, setModel] = useState<XpModel>(() => getPrefStr<XpModel>("xpModel", "advanced"));

  const load = useCallback((id: number, m: XpModel) => {
    setState("loading");
    getEntry(API, id, m)
      .then((e) => {
        setEntry(e);
        setState("ok");
      })
      .catch(() => setState("error"));
  }, []);

  useEffect(() => {
    const id = getStoredEntryId();
    if (!id) {
      setState("nolink");
      return;
    }
    load(id, model);
  }, [load, model]);

  function pickModel(m: XpModel) {
    setModel(m);
    setPrefStr("xpModel", m);
  }

  if (state === "nolink")
    return (
      <>
        <PageHeader title="Squad" />
        <EmptyState title="No team linked" hint="Link your FPL team ID on the home page." />
      </>
    );

  return (
    <>
      <PageHeader
        title="Squad"
        description={
          entry
            ? `${entry.manager_name} · picks from GW ${entry.picks_gameweek_id ?? "—"}`
            : undefined
        }
      />

      <div className="mb-3 flex items-center gap-2">
        <span className="text-xs text-fg-muted">xP model</span>
        <div className="inline-flex overflow-hidden rounded-md border border-border">
          {(["advanced", "basic"] as const).map((m) => (
            <Button
              key={m}
              size="sm"
              variant={model === m ? "default" : "ghost"}
              className="rounded-none border-0"
              onClick={() => pickModel(m)}
            >
              {m === "advanced" ? "Advanced" : "Basic"}
            </Button>
          ))}
        </div>
        {entry?.model && MODEL_LABEL[entry.model] && (
          <Badge variant="outline">{MODEL_LABEL[entry.model]} live</Badge>
        )}
      </div>

      {state === "error" && <p className="text-sm text-danger">Could not load squad.</p>}
      {state === "loading" && (
        <div className="space-y-2">
          {Array.from({ length: 11 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      )}
      {entry && state === "ok" && (
        <Card className="p-1.5">
          <DataTable
            rows={entry.picks}
            rowKey={(p) => p.player_id}
            initialSort={{ key: "slot", dir: "asc" }}
            emptyTitle="No picks for this gameweek yet"
            columns={[
              { key: "slot", header: "#", align: "right", sortable: true, className: "text-fg-muted" },
              { key: "web_name", header: "Player", className: "font-medium" },
              { key: "position", header: "Pos", className: "text-fg-muted" },
              {
                key: "now_cost",
                header: "£",
                align: "right",
                sortable: true,
                render: (p) => (p.now_cost / 10).toFixed(1),
              },
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
                  p.is_captain ? (
                    <Badge variant="primary">C</Badge>
                  ) : p.is_vice ? (
                    <Badge>V</Badge>
                  ) : null,
              },
            ]}
          />
        </Card>
      )}
    </>
  );
}
