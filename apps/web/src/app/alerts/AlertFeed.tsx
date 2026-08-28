"use client";

import { AlertTriangle, CalendarClock, Clock, Layers } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
} from "@/components/ui";
import {
  type Alert,
  getAlerts,
  getEntrySettings,
  markAlertsSeen,
  updateEntrySettings,
} from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";
import { PushToggle } from "./PushToggle";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const TYPE_META: Record<string, { bar: string; icon: React.ReactNode }> = {
  availability: { bar: "border-l-danger", icon: <AlertTriangle className="size-4 text-danger" /> },
  bgw: { bar: "border-l-warning", icon: <Layers className="size-4 text-warning" /> },
  dgw: { bar: "border-l-positive", icon: <Layers className="size-4 text-positive" /> },
  deadline: { bar: "border-l-primary", icon: <CalendarClock className="size-4 text-primary" /> },
};
const PRESETS = [1440, 120, 60, 30];
const PRESET_LABEL: Record<number, string> = { 1440: "24h", 120: "2h", 60: "1h", 30: "30m" };

export function AlertFeed() {
  const [entryId, setEntryId] = useState<number | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cap, setCap] = useState("");
  const [offsets, setOffsets] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => setEntryId(getStoredEntryId()), []);

  const load = useCallback(() => {
    if (entryId == null) return;
    getAlerts(API, entryId)
      .then((f) => {
        setAlerts(f.alerts);
        setErr(null);
      })
      .catch(() => setErr("Could not load alerts."));
  }, [entryId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (entryId == null) return;
    getEntrySettings(API, entryId)
      .then((s) => {
        setCap(s.alert_cap == null ? "" : String(s.alert_cap));
        setOffsets(s.reminder_offsets.join(", "));
      })
      .catch(() => undefined);
  }, [entryId]);

  const parseOffsets = (text: string) =>
    text
      .split(",")
      .map((s) => Number(s.trim()))
      .filter((n) => Number.isFinite(n) && n > 0);

  const saveSettings = (next: number[]) => {
    if (entryId == null) return;
    updateEntrySettings(API, entryId, {
      alertCap: cap === "" ? null : Number(cap),
      reminderOffsets: next,
    })
      .then((s) => setOffsets(s.reminder_offsets.join(", ")))
      .then(load)
      .catch(() => setErr("Could not save settings."));
  };

  const togglePreset = (m: number) => {
    const cur = new Set(parseOffsets(offsets));
    cur.has(m) ? cur.delete(m) : cur.add(m);
    saveSettings([...cur].sort((a, b) => b - a));
  };

  if (entryId == null)
    return (
      <>
        <PageHeader title="Alerts" />
        <EmptyState title="Link your team first" hint="Alerts are per linked team." />
      </>
    );

  const activeSet = new Set(parseOffsets(offsets));

  return (
    <>
      <PageHeader
        title="Alerts"
        description="Availability changes, blank/double gameweeks, deadline reminders."
        actions={
          <div className="flex items-center gap-2">
            <PushToggle />
            <Button
              size="sm"
              variant="outline"
              onClick={() => markAlertsSeen(API, entryId).then(load)}
            >
              Mark all read
            </Button>
          </div>
        }
      />

      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Settings</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-4 text-sm text-fg-muted">
          <label className="flex items-center gap-2">
            Max alerts
            <Input
              className="w-16"
              value={cap}
              onChange={(e) => setCap(e.target.value.replace(/[^0-9]/g, ""))}
              placeholder="∞"
            />
            <Button size="sm" variant="secondary" onClick={() => saveSettings(parseOffsets(offsets))}>
              Save
            </Button>
          </label>
          <div className="flex items-center gap-2">
            <Clock className="size-4" />
            Reminders
            {PRESETS.map((m) => (
              <Button
                key={m}
                size="sm"
                variant={activeSet.has(m) ? "default" : "outline"}
                onClick={() => togglePreset(m)}
              >
                {PRESET_LABEL[m]}
              </Button>
            ))}
            <Input
              className="w-40"
              value={offsets}
              onChange={(e) => setOffsets(e.target.value)}
              placeholder="minutes, comma-separated"
            />
            <Button size="sm" variant="secondary" onClick={() => saveSettings(parseOffsets(offsets))}>
              Save
            </Button>
          </div>
        </CardContent>
      </Card>

      {err && <p className="text-sm text-danger">{err}</p>}

      {alerts.length === 0 ? (
        <EmptyState title="No alerts right now" hint="Check back closer to the deadline." />
      ) : (
        <div className="space-y-2">
          {alerts.map((a) => {
            const meta = TYPE_META[a.type] ?? { bar: "border-l-border", icon: null };
            return (
              <Card
                key={a.id}
                className={`border-l-4 ${meta.bar} ${a.seen ? "opacity-60" : ""}`}
              >
                <CardContent className="flex items-start gap-3 p-3">
                  <div className="mt-0.5">{meta.icon}</div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between gap-3 text-sm font-medium">
                      <span>{a.title}</span>
                      <Badge>p{a.priority}</Badge>
                    </div>
                    <p className="mt-0.5 text-sm text-fg-muted">{a.body}</p>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
