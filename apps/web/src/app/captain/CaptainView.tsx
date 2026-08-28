"use client";

import { Crown } from "lucide-react";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Select,
  Skeleton,
} from "@/components/ui";
import { type CaptainAdvice, type CaptainPick, getCaptain } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";
import { getPref, setPref } from "@/lib/prefs";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function PickList({ picks }: { picks: CaptainPick[] }) {
  return (
    <ol className="space-y-1.5">
      {picks.map((p, i) => (
        <li
          key={p.player_id}
          className={cn(
            "flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-sm",
            i === 0 && "bg-primary/10 ring-1 ring-primary/40",
          )}
        >
          <span>
            <Badge className="mr-2">{i + 1}</Badge>
            {p.web_name}{" "}
            <span className="text-fg-muted">
              {p.team_short} · {p.position}
            </span>
          </span>
          <span className="tabular-nums text-fg-muted">{p.xp} xP</span>
        </li>
      ))}
    </ol>
  );
}

export function CaptainView() {
  const [entryId, setEntryId] = useState<number | null>(null);
  const [horizon, setHorizon] = useState(3);
  const [data, setData] = useState<CaptainAdvice | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setEntryId(getStoredEntryId());
    setHorizon(getPref("captainHorizon", 3));
  }, []);

  useEffect(() => {
    if (entryId == null) return;
    setErr(null);
    setData(null);
    getCaptain(API, entryId, horizon)
      .then(setData)
      .catch(() => setErr("Could not load captain advice."));
  }, [entryId, horizon]);

  if (entryId == null)
    return (
      <>
        <PageHeader title="AI Captain" />
        <EmptyState title="Link your team first" hint="Captain picks are based on your squad." />
      </>
    );

  return (
    <>
      <PageHeader
        title="AI Captain"
        description="Best captain from your XI and globally, by projected points."
        actions={
          <label className="flex items-center gap-2 text-sm text-fg-muted">
            Horizon
            <Select
              value={horizon}
              onChange={(e) => {
                const h = Number(e.target.value);
                setHorizon(h);
                setPref("captainHorizon", h);
              }}
            >
              {[1, 2, 3, 4, 5].map((h) => (
                <option key={h} value={h}>
                  {h}
                </option>
              ))}
            </Select>
          </label>
        }
      />

      {err && <p className="text-sm text-danger">{err}</p>}

      {!data && !err && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      )}

      {data && (
        <div className="grid gap-4 sm:grid-cols-2">
          {(["constrained", "unconstrained"] as const).map((kind) => (
            <Card key={kind}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Crown className="size-4 text-primary" />
                  {kind === "constrained" ? "From your XI" : "Anyone"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <PickList picks={data[kind]} />
                <p className="rounded-md bg-surface-2 px-3 py-2 text-sm text-fg-muted">
                  {data.rationale[kind]}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {data?.rationale_source === "template" && (
        <p className="mt-3 text-xs text-fg-muted">
          AI rationale unavailable — showing a summary. Add a Gemini key to enable it.
        </p>
      )}
    </>
  );
}
