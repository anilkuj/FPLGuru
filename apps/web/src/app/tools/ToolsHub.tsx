"use client";

import { useEffect, useState } from "react";

import {
  type CalendarWeek,
  getCalendar,
  getOverpowered,
  getTemplate,
  getTrends,
  type OverpoweredXI,
  type TemplateXI,
  type Trends,
} from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const TABS = ["Trends", "Template", "Calendar", "Overpowered XI"] as const;
type Tab = (typeof TABS)[number];

function TrendList({ title, rows }: { title: string; rows: Trends["transfers_in"] }) {
  return (
    <div>
      <p className="text-xs font-semibold text-gray-500">{title}</p>
      <ul className="mt-1 text-sm">
        {rows.map((r) => (
          <li key={r.player_id} className="flex justify-between gap-4">
            <span>{r.web_name}</span>
            <span className="text-gray-400">{r.value.toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ToolsHub() {
  const [tab, setTab] = useState<Tab>("Trends");
  const [trends, setTrends] = useState<Trends | null>(null);
  const [template, setTemplate] = useState<TemplateXI | null>(null);
  const [calendar, setCalendar] = useState<CalendarWeek[] | null>(null);
  const [op, setOp] = useState<OverpoweredXI | null>(null);
  const [horizon, setHorizon] = useState(5);
  const [range, setRange] = useState<[number, number]>([1, 8]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const fail = () => setErr("Could not load this tool.");
    if (tab === "Trends" && !trends) getTrends(API).then(setTrends).catch(fail);
    if (tab === "Template" && !template) getTemplate(API).then(setTemplate).catch(fail);
  }, [tab, trends, template]);

  useEffect(() => {
    if (tab === "Calendar")
      getCalendar(API, range[0], range[1])
        .then(setCalendar)
        .catch(() => setErr("Could not load this tool."));
  }, [tab, range]);

  useEffect(() => {
    if (tab === "Overpowered XI")
      getOverpowered(API, horizon)
        .then(setOp)
        .catch(() => setErr("Could not load this tool."));
  }, [tab, horizon]);

  return (
    <>
      <div className="mt-3 flex flex-wrap gap-2 text-sm">
        {TABS.map((t) => (
          <button
            key={t}
            className={`rounded border px-2 py-1 ${t === tab ? "bg-sky-200 border-sky-300" : ""}`}
            onClick={() => {
              setErr(null);
              setTab(t);
            }}
          >
            {t}
          </button>
        ))}
      </div>
      {err && <p className="mt-3 text-sm text-red-600">{err}</p>}

      {tab === "Trends" && trends && (
        <div className="mt-4 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <TrendList title="Most transferred in" rows={trends.transfers_in} />
          <TrendList title="Most transferred out" rows={trends.transfers_out} />
          <TrendList title="Price risers" rows={trends.price_risers} />
          <TrendList title="Price fallers" rows={trends.price_fallers} />
          <TrendList title="Most owned" rows={trends.most_owned} />
        </div>
      )}

      {tab === "Template" && template && (
        <div className="mt-4">
          <p className="text-sm text-gray-500">
            {template.formation} · combined ownership {template.template_ownership}%
          </p>
          <ul className="mt-2 text-sm">
            {template.xi.map((p) => (
              <li key={p.player_id} className="flex justify-between gap-4">
                <span>
                  <span className="text-gray-400">{p.position}</span> {p.web_name}
                </span>
                <span className="text-gray-400">{p.selected_by_percent}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {tab === "Calendar" && (
        <div className="mt-4">
          <label className="text-sm text-gray-500">
            GW{" "}
            <input
              className="w-14 rounded border px-1"
              type="number"
              value={range[0]}
              onChange={(e) => setRange([Number(e.target.value) || 1, range[1]])}
            />{" "}
            to{" "}
            <input
              className="w-14 rounded border px-1"
              type="number"
              value={range[1]}
              onChange={(e) => setRange([range[0], Number(e.target.value) || 1])}
            />
          </label>
          <table className="mt-3 text-sm border-collapse">
            <tbody>
              {(calendar ?? []).map((c) => (
                <tr key={c.gameweek_id} className="border-t">
                  <td className="px-2 py-1 font-medium">GW{c.gameweek_id}</td>
                  <td className="px-2 py-1 text-emerald-600">
                    {c.doubles.length ? `DGW: ${c.doubles.join(", ")}` : ""}
                  </td>
                  <td className="px-2 py-1 text-amber-600">
                    {c.blanks.length ? `BGW: ${c.blanks.join(", ")}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-gray-400">Values are FPL team ids.</p>
        </div>
      )}

      {tab === "Overpowered XI" && (
        <div className="mt-4">
          <label className="text-sm text-gray-500">
            Horizon{" "}
            <select
              className="rounded border px-2 py-1"
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
            >
              {Array.from({ length: 10 }, (_, i) => i + 1).map((h) => (
                <option key={h} value={h}>
                  {h}
                </option>
              ))}
            </select>
          </label>
          {op && (
            <>
              <p className="mt-2 text-sm text-gray-500">
                {op.formation} · {op.total_xp} xP · £{(op.total_cost / 10).toFixed(1)}m
              </p>
              <ul className="mt-2 text-sm">
                {op.xi.map((p) => (
                  <li key={p.player_id} className="flex justify-between gap-4">
                    <span>
                      <span className="text-gray-400">{p.position}</span> {p.web_name}
                    </span>
                    <span className="text-gray-400">{p.xp} xP</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </>
  );
}
