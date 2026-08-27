"use client";

import { useEffect, useMemo, useState } from "react";

import { type FdrGridData, getFdr } from "@/lib/api";
import { getPref, setPref } from "@/lib/prefs";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const CLR = ["", "bg-emerald-200", "bg-lime-200", "bg-amber-200", "bg-orange-200", "bg-red-300"];

export function FdrGrid() {
  const [horizon, setHorizon] = useState(5);
  const [data, setData] = useState<FdrGridData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setHorizon(getPref("fdrHorizon", 5));
  }, []);

  useEffect(() => {
    setErr(null);
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
      <label className="mt-2 block text-sm text-gray-500">
        Horizon{" "}
        <select
          value={horizon}
          onChange={(e) => {
            const h = Number(e.target.value);
            setHorizon(h);
            setPref("fdrHorizon", h);
          }}
          className="border rounded px-2 py-1"
        >
          {Array.from({ length: 10 }, (_, i) => i + 1).map((h) => (
            <option key={h} value={h}>
              {h}
            </option>
          ))}
        </select>
      </label>
      {err && <p className="mt-3 text-sm text-red-600">{err}</p>}
      {data && (
        <div className="mt-4 overflow-x-auto">
          <table className="text-sm border-collapse">
            <thead>
              <tr>
                <th className="text-left px-2 py-1">Team</th>
                <th className="px-2 py-1">Avg</th>
                {cols.map((g) => (
                  <th key={g} className="px-2 py-1">
                    GW{g}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.teams.map((t) => (
                <tr key={t.team_id} className="border-t">
                  <td className="px-2 py-1 font-medium">{t.short_name}</td>
                  <td className="px-2 py-1 text-center text-gray-500">{t.avg_fdr ?? "—"}</td>
                  {cols.map((g) => {
                    const fs = t.fixtures.filter((f) => f.gameweek_id === g);
                    return (
                      <td key={g} className="px-1 py-1 text-center">
                        {fs.length === 0 ? (
                          <span className="text-gray-300">—</span>
                        ) : (
                          fs.map((f, i) => (
                            <span
                              key={i}
                              className={`inline-block rounded px-1 mx-0.5 ${CLR[f.band] ?? ""}`}
                            >
                              {f.opponent_short}
                              {f.is_home ? " (H)" : " (A)"}
                            </span>
                          ))
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
