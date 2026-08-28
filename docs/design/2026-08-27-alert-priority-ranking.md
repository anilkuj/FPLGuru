# Alert Priority Ranking

**Status:** accepted · 2026-08-27 · owner: FPLGuru
**Context:** PRD next-steps §11.4. Feeds sub-plan P1e.

## Problem

When a linked team has more pending alerts than its `alert_cap`, we must decide
which to surface and which to suppress. We need a deterministic, explainable score.

## Score

`score_alert` returns an integer 0–100 (higher = more important). It is a sum of
additive terms, then clamped:

| Term | Value | When |
|---|---|---|
| base: availability | 60 | player availability changed |
| base: bgw | 45 | a team the user owns has no fixture next GW |
| base: dgw | 40 | a team the user owns has 2+ fixtures next GW |
| base: other | 20 | any future generator without an explicit base |
| captaincy | +25 | the affected player is the user's (vice-)captain |
| starting XI | +15 | the affected player has multiplier > 0 (and not captain) |
| hard unavailability | +15 | availability alert whose status is i / s / u (not just "doubtful") |
| pre-deadline | +10 | the current GW deadline has not passed |

Clamp to `[0, 100]`. Ties break by `alert.id` ascending (older first) so ordering
is stable across re-runs.

## Why these weights

- Availability outranks DGW/BGW: a player who won't play is an immediate lineup
  problem; a blank/double is planning information with a longer runway.
- BGW slightly above DGW: a blank can leave you short a starter; a double is upside.
- Captaincy > XI > bench/owned-only: impact scales with how much the pick counts.
- "Hard out" (injured/suspended/unavailable) above "doubtful": less ambiguity, more
  urgency.
- Pre-deadline bump: the alert is still actionable this GW.

## Worked examples

| Alert | Terms | Score |
|---|---|---|
| Captain ruled out (status i), pre-deadline | 60 + 25 + 15 + 10 | 100 (clamped) |
| Bench player doubtful (75%), pre-deadline | 60 + 10 | 70 |
| DGW for a team whose player is your captain, pre-deadline | 40 + 25 + 10 | 75 |
| BGW for a team you own on the bench, post-deadline | 45 | 45 |

## Cap application

Per linked team, per gameweek: sort that GW's alerts by `(-score, id)`; the first
`alert_cap` stay visible, the rest get `suppressed = true` (still stored, hidden
from the default feed, visible with `?include_suppressed=true`). `alert_cap = NULL`
(default) suppresses nothing.

## Deferred generators

`price_change` (needs a `now_cost` history snapshot) and `fdr_shift` (needs stored
per-GW FDR snapshots) are out of scope for P1e v1; when added they slot in with a
base weight in the table above.
