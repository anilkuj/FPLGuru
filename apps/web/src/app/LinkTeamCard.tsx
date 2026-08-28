"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@/components/ui";
import { linkEntry } from "@/lib/api";
import { getStoredEntryId, setStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function LinkTeamCard() {
  const [id, setId] = useState("");
  const [linked, setLinked] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  useEffect(() => setLinked(getStoredEntryId()), []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const n = Number(id);
      if (!Number.isInteger(n) || n <= 0) throw new Error("Enter a numeric FPL team ID");
      await linkEntry(API, n);
      setStoredEntryId(n);
      router.push("/squad");
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Failed to link");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card id="link" className="max-w-xl">
      <CardHeader>
        <CardTitle className="text-base">Link your FPL team</CardTitle>
        <p className="text-sm text-fg-muted">
          Your team ID is the number in your FPL &ldquo;Points&rdquo; page URL:{" "}
          <code className="text-fg">/entry/&lt;ID&gt;/event/…</code>
        </p>
      </CardHeader>
      <CardContent>
        {linked != null && (
          <p className="mb-3 text-sm text-fg-muted">
            Linked to team <span className="text-fg">#{linked}</span>.{" "}
            <button
              className="text-primary hover:underline"
              onClick={() => {
                setStoredEntryId(0);
                setLinked(null);
              }}
            >
              unlink
            </button>
          </p>
        )}
        <form onSubmit={submit} className="flex gap-2">
          <Input
            value={id}
            onChange={(e) => setId(e.target.value)}
            inputMode="numeric"
            placeholder="e.g. 1234567"
          />
          <Button disabled={busy} type="submit">
            {busy ? "…" : "Link"}
          </Button>
        </form>
        {err && <p className="mt-2 text-sm text-danger">{err}</p>}
      </CardContent>
    </Card>
  );
}
