"use client";

import { useEffect, useState } from "react";

import { DataTable } from "@/components/DataTable";
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Select,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui";
import { EmptyState } from "@/components/EmptyState";
import {
  type CalendarWeek,
  getCalendar,
  getOverpowered,
  getTemplate,
  getTransparency,
  getTrends,
  getXgSnapshot,
  type OverpoweredXI,
  type TemplateXI,
  type Transparency,
  type Trends,
  type XgSnapshot,
} from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function TrendCard({ title, rows }: { title: string; rows: Trends["transfers_in"] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {rows.map((r) => (
          <div key={r.player_id} className="flex items-center justify-between text-sm">
            <span>{r.web_name}</span>
            <Badge>{r.value.toLocaleString()}</Badge>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function ToolsHub() {
  const [trends, setTrends] = useState<Trends | null>(null);
  const [template, setTemplate] = useState<TemplateXI | null>(null);
  const [calendar, setCalendar] = useState<CalendarWeek[] | null>(null);
  const [op, setOp] = useState<OverpoweredXI | null>(null);
  const [xg, setXg] = useState<XgSnapshot | null>(null);
  const [xgPos, setXgPos] = useState("");
  const [tr, setTr] = useState<Transparency | null>(null);
  const [horizon, setHorizon] = useState(5);
  const [from, setFrom] = useState(1);
  const [to, setTo] = useState(8);
  const [tab, setTab] = useState("trends");

  useEffect(() => {
    if (tab === "trends" && !trends) getTrends(API).then(setTrends).catch(() => undefined);
    if (tab === "template" && !template)
      getTemplate(API).then(setTemplate).catch(() => undefined);
  }, [tab, trends, template]);
  useEffect(() => {
    if (tab === "calendar") getCalendar(API, from, to).then(setCalendar).catch(() => undefined);
  }, [tab, from, to]);
  useEffect(() => {
    if (tab === "op") getOverpowered(API, horizon).then(setOp).catch(() => undefined);
  }, [tab, horizon]);
  useEffect(() => {
    if (tab === "xg")
      getXgSnapshot(API, 6, xgPos || undefined).then(setXg).catch(() => undefined);
  }, [tab, xgPos]);
  useEffect(() => {
    if (tab === "model" && !tr) getTransparency(API, 6).then(setTr).catch(() => undefined);
  }, [tab, tr]);

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList>
        <TabsTrigger value="trends">Trends</TabsTrigger>
        <TabsTrigger value="template">Template</TabsTrigger>
        <TabsTrigger value="calendar">Calendar</TabsTrigger>
        <TabsTrigger value="op">Overpowered XI</TabsTrigger>
        <TabsTrigger value="xg">xG</TabsTrigger>
        <TabsTrigger value="model">Model</TabsTrigger>
      </TabsList>

      <TabsContent value="trends">
        {trends && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <TrendCard title="Most transferred in" rows={trends.transfers_in} />
            <TrendCard title="Most transferred out" rows={trends.transfers_out} />
            <TrendCard title="Price risers" rows={trends.price_risers} />
            <TrendCard title="Price fallers" rows={trends.price_fallers} />
            <TrendCard title="Most owned %" rows={trends.most_owned} />
          </div>
        )}
      </TabsContent>

      <TabsContent value="template">
        {template && (
          <Card>
            <CardHeader>
              <CardTitle>
                Template XI · {template.formation} ·{" "}
                <span className="text-fg-muted">
                  {template.template_ownership}% combined ownership
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {template.xi.map((p) => (
                <div key={p.player_id} className="flex items-center justify-between text-sm">
                  <span>
                    <span className="mr-2 text-xs text-fg-muted">{p.position}</span>
                    {p.web_name}
                  </span>
                  <span className="text-fg-muted">{p.selected_by_percent}%</span>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </TabsContent>

      <TabsContent value="calendar">
        <div className="mb-3 flex items-center gap-2 text-sm text-fg-muted">
          GW
          <Input
            className="w-16"
            type="number"
            value={from}
            onChange={(e) => setFrom(Number(e.target.value) || 1)}
          />
          to
          <Input
            className="w-16"
            type="number"
            value={to}
            onChange={(e) => setTo(Number(e.target.value) || 1)}
          />
        </div>
        <Card>
          <CardContent className="space-y-2 pt-5">
            {(calendar ?? []).map((c) => (
              <div key={c.gameweek_id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="w-12 font-medium">GW{c.gameweek_id}</span>
                {c.doubles.map((t) => (
                  <Badge key={`d${t}`} variant="positive">
                    DGW {t}
                  </Badge>
                ))}
                {c.blanks.map((t) => (
                  <Badge key={`b${t}`} variant="warning">
                    BGW {t}
                  </Badge>
                ))}
                {c.doubles.length === 0 && c.blanks.length === 0 && (
                  <span className="text-fg-muted">—</span>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
        <p className="mt-1 text-xs text-fg-muted">Values are FPL team ids.</p>
      </TabsContent>

      <TabsContent value="op">
        <div className="mb-3 flex items-center gap-2 text-sm text-fg-muted">
          Horizon
          <Select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
            {Array.from({ length: 10 }, (_, i) => i + 1).map((h) => (
              <option key={h} value={h}>
                {h}
              </option>
            ))}
          </Select>
        </div>
        {op && (
          <Card>
            <CardHeader>
              <CardTitle>
                {op.formation} · {op.total_xp} xP · £{(op.total_cost / 10).toFixed(1)}m
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {op.xi.map((p) => (
                <div key={p.player_id} className="flex items-center justify-between text-sm">
                  <span>
                    <span className="mr-2 text-xs text-fg-muted">{p.position}</span>
                    {p.web_name}
                  </span>
                  <span className="text-fg-muted">{p.xp} xP</span>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </TabsContent>

      <TabsContent value="xg">
        <div className="mb-3 flex items-center gap-2 text-sm text-fg-muted">
          Position
          <Select value={xgPos} onChange={(e) => setXgPos(e.target.value)}>
            <option value="">All</option>
            {["GK", "DEF", "MID", "FWD"].map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </Select>
        </div>
        <Card className="p-1.5">
          <DataTable
            rows={(xg?.players ?? []).slice(0, 40)}
            rowKey={(r) => r.player_id}
            initialSort={{ key: "xg", dir: "desc" }}
            emptyTitle="No xG data yet"
            emptyHint="Add a PitchAPI key and the sync_xg task fills this after matches."
            columns={[
              { key: "web_name", header: "Player", className: "font-medium" },
              { key: "position", header: "Pos", className: "text-fg-muted" },
              { key: "xg", header: "xG", align: "right", sortable: true },
              { key: "xag", header: "xA", align: "right", sortable: true },
              {
                key: "minutes",
                header: "min",
                align: "right",
                sortable: true,
                className: "text-fg-muted",
              },
            ]}
          />
        </Card>
      </TabsContent>

      <TabsContent value="model">
        <ModelTab tr={tr} />
      </TabsContent>
    </Tabs>
  );
}

const POS_ROWS = ["GK", "DEF", "MID", "FWD", "ALL"];

function MetricTable({
  title,
  data,
}: {
  title: string;
  data: Record<string, { n: number; mae: number; rmse: number; bias: number }>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead className="text-fg-muted">
            <tr>
              <th className="text-left font-medium">Pos</th>
              <th className="text-right font-medium">n</th>
              <th className="text-right font-medium">MAE</th>
              <th className="text-right font-medium">RMSE</th>
              <th className="text-right font-medium">bias</th>
            </tr>
          </thead>
          <tbody>
            {POS_ROWS.map((p) => {
              const m = data[p];
              return (
                <tr key={p} className={p === "ALL" ? "font-semibold" : undefined}>
                  <td>{p}</td>
                  <td className="text-right">{m?.n ?? 0}</td>
                  <td className="text-right">{m ? m.mae.toFixed(2) : "—"}</td>
                  <td className="text-right">{m ? m.rmse.toFixed(2) : "—"}</td>
                  <td className="text-right">{m ? m.bias.toFixed(2) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function ModelTab({ tr }: { tr: Transparency | null }) {
  if (!tr) return null;
  const hasData =
    tr.last_gw != null ||
    tr.models.some((m) => (tr.by_position[m]?.ALL?.n ?? 0) > 0);
  if (!hasData)
    return (
      <EmptyState
        title="No finished gameweeks with predictions yet"
        hint="Accuracy shows up here after the first gameweek completes."
      />
    );
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {tr.models.map((m) => (
          <MetricTable key={m} title={`${m} — overall`} data={tr.by_position[m] ?? {}} />
        ))}
        {tr.models.map((m) => (
          <MetricTable
            key={`${m}-roll`}
            title={`${m} — last ${tr.rolling_window} GW`}
            data={tr.rolling[m] ?? {}}
          />
        ))}
      </div>

      {tr.last_gw && (
        <Card className="p-1.5">
          <div className="px-2 py-1.5 text-sm font-semibold">
            GW{tr.last_gw.gameweek_id} — projection vs actual
          </div>
          <DataTable
            rows={tr.last_gw.rows}
            rowKey={(r) => `${r.player_id}-${r.model}`}
            initialSort={{ key: "delta", dir: "desc" }}
            emptyTitle="No rows"
            columns={[
              { key: "web_name", header: "Player", className: "font-medium" },
              { key: "position", header: "Pos", className: "text-fg-muted" },
              { key: "model", header: "Model", className: "text-fg-muted" },
              {
                key: "predicted",
                header: "Proj",
                align: "right",
                sortable: true,
                render: (r) => r.predicted.toFixed(1),
              },
              {
                key: "actual",
                header: "Actual",
                align: "right",
                sortable: true,
                render: (r) => r.actual.toFixed(0),
              },
              {
                key: "delta",
                header: "Δ",
                align: "right",
                sortable: true,
                render: (r) => (
                  <Badge variant={r.delta >= 0 ? "positive" : "danger"}>
                    {r.delta >= 0 ? "+" : ""}
                    {r.delta.toFixed(1)}
                  </Badge>
                ),
              },
            ]}
          />
        </Card>
      )}
    </div>
  );
}
