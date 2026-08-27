"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { linkEntry } from "@/lib/api";
import { setStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default function Home() {
  const [id, setId] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();

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
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to link");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="p-8 max-w-md">
      <h1 className="text-2xl font-semibold">Link your FPL team</h1>
      <p className="mt-1 text-sm text-gray-500">
        Your team ID is in the URL on the FPL &ldquo;Points&rdquo; page:
        <code className="mx-1">/entry/&lt;ID&gt;/event/…</code>
      </p>
      <form onSubmit={submit} className="mt-4 flex gap-2">
        <input
          value={id}
          onChange={(e) => setId(e.target.value)}
          inputMode="numeric"
          placeholder="e.g. 1234567"
          className="border rounded px-3 py-2 flex-1"
        />
        <button disabled={busy} className="border rounded px-4 py-2 disabled:opacity-50">
          {busy ? "…" : "Link"}
        </button>
      </form>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
    </main>
  );
}
