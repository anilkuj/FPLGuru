"use client";

import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Card, Select, Skeleton } from "@/components/ui";
import { type FdrGridData, getFdr } from "@/lib/api";
import { getPref, setPref } from "@/lib/prefs";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// difficulty band 1..5 -> cell colour + text colour
const BAND: Record<number, string> = {
  1: "bg-[#1f8a53] text-white",
  2: "bg-[#3fae5f] text-white",
  3: "bg-[#d8a13a] text-black",
  4: "bg-[#e07f3a] text-black",
  5: "bg-[#d0445a] text-white",
};

export function FdrGrid() {
  const [horizon, setHorizon] = useState(5);
  const [data, setData] = useState<FdrGridData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => setHorizon(getPref("fdrHorizon", 5)), []);

  useEffect(() => {
    setErr(null);
    setData(null);
    getFdr(API, horizon)
      .then(setData)
      .catch(() => setErr("Could not load FDR."));
  }, [horizon]);

  const cols = useMemo(
    () => (data ? Array.from({ length: data.horizon }, (_, i) => data.start_gw + i) : []),
    [data],
  );

  return (
    <>
      <PageHeader
        title="Fixture difficulty"
        description="Opponent strength blended with recent goals form. Easiest run first."
        actions={
          <label className="flex items-center gap-2 text-sm text-fg-muted">
            Horizon
            <Select
              value={horizon}
              onChange={(e) => {
                const h = Number(e.target.value);
                setHorizon(h);
                setPref("fdrHorizon", h);
              }}
            >
              {Array.from({ length: 10 }, (_, i) => i + 1).map((h) => (
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
        <Card className="p-4">
          <div className="space-y-2">
            {Array.from({ length: 12 }).map((_, i) => (
              <Skeleton key={i} className="h-7 w-full" />
            ))}
          </div>
        </Card>
      )}

      {data && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead className="bg-surface-2 text-xs uppercase tracking-wide text-fg-muted">
                <tr>
                  <th className="sticky left-0 z-10 bg-surface-2 px-3 py-2 text-left">Team</th>
                  <th className="px-3 py-2 text-right">Avg</th>
                  {cols.map((g) => (
                    <th key={g} className="px-2 py-2 text-center">
                      GW{g}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.teams.map((t) => (
                  <tr key={t.team_id} className="border-t border-border/60">
                    <td className="sticky left-0 z-10 bg-surface px-3 py-1.5 font-medium">
                      {t.short_name}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-fg-muted">
                      {t.avg_fdr ?? "—"}
                    </td>
                    {cols.map((g) => {
                      const fs = t.fixtures.filter((f) => f.gameweek_id === g);
                      return (
                        <td key={g} className="px-1 py-1 text-center">
                          {fs.length === 0 ? (
                            <span className="text-fg-muted/40">—</span>
                          ) : (
                            <div className="flex flex-wrap justify-center gap-0.5">
                              {fs.map((f, i) => (
                                <span
                                  key={i}
                                  className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${
                                    BAND[f.band] ?? "bg-surface-2"
                                  }`}
                                  title={`${f.opponent_short} ${f.is_home ? "home" : "away"} · ${f.fdr.toFixed(2)}`}
                                >
                                  {f.opponent_short}
                                  {f.is_home ? "" : " ·a"}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
