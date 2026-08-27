export type SyncStatus = {
  sources: Record<string, { status: string; as_of: string | null }>;
};

export async function fetchStatus(base: string): Promise<SyncStatus> {
  const res = await fetch(`${base}/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(`status ${res.status}`);
  return (await res.json()) as SyncStatus;
}

export type EntryPick = {
  slot: number;
  player_id: number;
  web_name: string;
  position: string;
  now_cost: number;
  multiplier: number;
  is_captain: boolean;
  is_vice: boolean;
  xp: number;
};
export type Entry = {
  fpl_entry_id: number;
  manager_name: string;
  last_synced_at: string | null;
  picks_gameweek_id: number | null;
  picks: EntryPick[];
};
export type EntryHistoryRow = {
  gameweek_id: number;
  points: number;
  total_points: number;
  overall_rank: number | null;
  bank: number;
  team_value: number;
  transfers: number;
  transfer_cost: number;
  points_on_bench: number;
};

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`http ${res.status}`);
  return (await res.json()) as T;
}

export function linkEntry(base: string, id: number) {
  return fetch(`${base}/link/${id}`, { method: "POST" }).then(
    asJson<{ fpl_entry_id: number; manager_name: string; linked_team_id: number }>,
  );
}
export function getEntry(base: string, id: number) {
  return fetch(`${base}/entries/${id}`, { cache: "no-store" }).then(asJson<Entry>);
}
export function getEntryHistory(base: string, id: number) {
  return fetch(`${base}/entries/${id}/history`, { cache: "no-store" }).then(asJson<EntryHistoryRow[]>);
}

export type FdrFixture = {
  gameweek_id: number;
  opponent_short: string;
  is_home: boolean;
  fdr: number;
  att_fdr: number;
  def_fdr: number;
  band: number;
  opponent_form: { gf_pg: number; ga_pg: number } | null;
};
export type FdrTeam = {
  team_id: number;
  short_name: string;
  avg_fdr: number | null;
  fixtures: FdrFixture[];
};
export type FdrGridData = { start_gw: number; horizon: number; teams: FdrTeam[] };

export function getFdr(base: string, horizon: number, startGw?: number) {
  const q = new URLSearchParams({ horizon: String(horizon) });
  if (startGw) q.set("start_gw", String(startGw));
  return fetch(`${base}/fdr?${q}`, { cache: "no-store" }).then(asJson<FdrGridData>);
}
