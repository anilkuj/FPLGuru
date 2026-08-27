export type SyncStatus = {
  sources: Record<string, { status: string; as_of: string | null }>;
};

export async function fetchStatus(base: string): Promise<SyncStatus> {
  const res = await fetch(`${base}/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(`status ${res.status}`);
  return (await res.json()) as SyncStatus;
}
