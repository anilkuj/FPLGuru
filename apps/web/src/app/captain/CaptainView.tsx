"use client";

import { useEffect, useState } from "react";

import { type CaptainAdvice, type CaptainPick, getCaptain } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";
import { getPref, setPref } from "@/lib/prefs";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function PickList({ picks }: { picks: CaptainPick[] }) {
  return (
    <ol className="mt-2 text-sm">
      {picks.map((p, i) => (
        <li key={p.player_id} className="flex justify-between gap-4">
          <span>
            <span className="text-gray-400">{i + 1}.</span> {p.web_name}{" "}
            <span className="text-gray-400">
              {p.team_short} · {p.position}
            </span>
          </span>
          <span className="text-gray-500">{p.xp} xP</span>
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
    getCaptain(API, entryId, horizon)
      .then(setData)
      .catch(() => setErr("Could not load captain advice."));
  }, [entryId, horizon]);

  if (entryId == null)
    return <p className="mt-4 text-sm text-gray-500">Link your team first (Squad tab).</p>;

  return (
    <>
      <label className="mt-2 block text-sm text-gray-500">
        Horizon{" "}
        <select
          className="border rounded px-2 py-1"
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
        </select>
      </label>
      {err && <p className="mt-3 text-sm text-red-600">{err}</p>}
      {data && (
        <>
          <div className="mt-4 grid gap-6 sm:grid-cols-2">
            <section>
              <h2 className="text-sm font-semibold">From your XI</h2>
              <PickList picks={data.constrained} />
              <p className="mt-2 text-sm text-gray-600">{data.rationale.constrained}</p>
            </section>
            <section>
              <h2 className="text-sm font-semibold">Anyone</h2>
              <PickList picks={data.unconstrained} />
              <p className="mt-2 text-sm text-gray-600">{data.rationale.unconstrained}</p>
            </section>
          </div>
          {data.rationale_source === "template" && (
            <p className="mt-3 text-xs text-gray-400">
              AI rationale unavailable — showing a summary.
            </p>
          )}
        </>
      )}
    </>
  );
}
