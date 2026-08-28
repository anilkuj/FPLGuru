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

export async function asJson<T>(res: Response): Promise<T> {
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

export type LiveFixture = {
  id: number;
  home_team_id: number;
  away_team_id: number;
  home_score: number | null;
  away_score: number | null;
  started: boolean;
  finished: boolean;
  minutes: number;
};
export type LivePlayer = {
  player_id: number;
  web_name: string;
  team_id: number;
  position: string;
  minutes: number;
  live_points: number;
  bps: number;
  projected_bonus: number;
  total_points: number;
};
export type LiveSnapshot = {
  gameweek_id: number | null;
  updated_at: string | null;
  fixtures: LiveFixture[];
  players: LivePlayer[];
};

export function getLive(base: string) {
  return fetch(`${base}/gameweeks/current/live`, { cache: "no-store" }).then(
    asJson<LiveSnapshot>,
  );
}

export type Alert = {
  id: number;
  type: string;
  gameweek_id: number;
  player_id: number | null;
  priority: number;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  suppressed: boolean;
  seen: boolean;
  created_at: string;
};
export type AlertFeedData = { alerts: Alert[]; unseen: number };

export function getAlerts(base: string, entryId: number, includeSuppressed = false) {
  const q = includeSuppressed ? "?include_suppressed=true" : "";
  return fetch(`${base}/entries/${entryId}/alerts${q}`, { cache: "no-store" }).then(
    asJson<AlertFeedData>,
  );
}

export function markAlertsSeen(base: string, entryId: number, ids?: number[]) {
  return fetch(`${base}/entries/${entryId}/alerts/seen`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(ids ? { ids } : {}),
  }).then(asJson<{ marked: number }>);
}

export type EntrySettings = {
  fpl_entry_id: number;
  alert_cap: number | null;
  reminder_offsets: number[];
};

export function getEntrySettings(base: string, entryId: number) {
  return fetch(`${base}/entries/${entryId}/settings`, { cache: "no-store" }).then(
    asJson<EntrySettings>,
  );
}

export function updateEntrySettings(
  base: string,
  entryId: number,
  opts: { alertCap?: number | null; reminderOffsets?: number[] },
) {
  const body: Record<string, unknown> = { alert_cap: opts.alertCap ?? null };
  if (opts.reminderOffsets !== undefined) body.reminder_offsets = opts.reminderOffsets;
  return fetch(`${base}/entries/${entryId}/settings`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then(asJson<EntrySettings>);
}

export type MiniLeague = {
  league_id: number;
  league_name: string;
  entry_rank: number | null;
  entry_last_rank: number | null;
  delta: number | null;
};
export type StandingRow = {
  entry_id: number;
  entry_name: string;
  player_name: string;
  rank: number;
  last_rank: number | null;
  total: number;
  event_total: number;
  delta: number | null;
};
export type LeagueStandings = { league_id: number; standings: StandingRow[] };
export type RankPoint = {
  gameweek_id: number;
  overall_rank: number | null;
  points: number;
  total_points: number;
};

export function getEntryLeagues(base: string, entryId: number) {
  return fetch(`${base}/entries/${entryId}/leagues`, { cache: "no-store" }).then(
    asJson<MiniLeague[]>,
  );
}
export function getLeagueStandings(base: string, leagueId: number) {
  return fetch(`${base}/leagues/${leagueId}/standings`, { cache: "no-store" }).then(
    asJson<LeagueStandings>,
  );
}
export function searchLeague(base: string, leagueId: number, q: string) {
  return fetch(`${base}/leagues/${leagueId}/search?q=${encodeURIComponent(q)}`, {
    cache: "no-store",
  }).then(
    asJson<
      Array<Pick<StandingRow, "entry_id" | "entry_name" | "player_name" | "rank" | "total">>
    >,
  );
}
export function getRankHistory(base: string, entryId: number) {
  return fetch(`${base}/entries/${entryId}/rank-history`, { cache: "no-store" }).then(
    asJson<RankPoint[]>,
  );
}

export type TrendRow = { player_id: number; web_name: string; position: string; value: number };
export type Trends = {
  transfers_in: TrendRow[];
  transfers_out: TrendRow[];
  price_risers: TrendRow[];
  price_fallers: TrendRow[];
  most_owned: TrendRow[];
};
export type TemplatePlayer = {
  player_id: number;
  web_name: string;
  position: string;
  selected_by_percent: number;
};
export type TemplateXI = {
  formation: string;
  template_ownership: number;
  xi: TemplatePlayer[];
};
export type CalendarWeek = {
  gameweek_id: number;
  counts: Record<string, number>;
  blanks: number[];
  doubles: number[];
};
export type OverpoweredPlayer = {
  player_id: number;
  web_name: string;
  position: string;
  xp: number;
  now_cost: number;
};
export type OverpoweredXI = {
  formation: string;
  total_xp: number;
  total_cost: number;
  xi: OverpoweredPlayer[];
};

export function getTrends(base: string, limit = 10) {
  return fetch(`${base}/trends?limit=${limit}`, { cache: "no-store" }).then(asJson<Trends>);
}
export function getTemplate(base: string) {
  return fetch(`${base}/template`, { cache: "no-store" }).then(asJson<TemplateXI>);
}
export function getCalendar(base: string, fromGw: number, toGw: number) {
  return fetch(`${base}/calendar?from_gw=${fromGw}&to_gw=${toGw}`, { cache: "no-store" }).then(
    asJson<CalendarWeek[]>,
  );
}
export function getOverpowered(base: string, horizon = 5) {
  return fetch(`${base}/overpowered?horizon=${horizon}`, { cache: "no-store" }).then(
    asJson<OverpoweredXI>,
  );
}

export type CaptainPick = {
  player_id: number;
  web_name: string;
  position: string;
  team_short: string;
  xp: number;
};
export type CaptainAdvice = {
  gameweek_id: number;
  horizon: number;
  constrained: CaptainPick[];
  unconstrained: CaptainPick[];
  rationale: { constrained?: string; unconstrained?: string };
  rationale_source: "llm" | "template";
};

export function getCaptain(base: string, entryId: number, horizon = 3) {
  return fetch(`${base}/entries/${entryId}/captain?horizon=${horizon}`, {
    cache: "no-store",
  }).then(asJson<CaptainAdvice>);
}

export type XgRow = {
  player_id: number;
  web_name: string;
  position: string;
  team_id: number;
  xg: number;
  xag: number;
  minutes: number;
};
export type XgSnapshot = { from_gw: number | null; players: XgRow[] };

export function getXgSnapshot(base: string, last = 6, position?: string) {
  const q = new URLSearchParams({ last: String(last) });
  if (position) q.set("position", position);
  return fetch(`${base}/xg-snapshot?${q}`, { cache: "no-store" }).then(asJson<XgSnapshot>);
}
