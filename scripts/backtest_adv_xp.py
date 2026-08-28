"""Walk-forward backtest of the Advanced xP model vs the Basic model.

Writes a Markdown report with a per-position adv-vs-basic RMSE table.

    python scripts/backtest_adv_xp.py --csv data/historical/2024-25_merged_gw.csv
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from fplguru_ingest.historical import normalize_merged_gw
from fplguru_ml.backtest import walk_forward, walk_forward_adv
from fplguru_ml.frame import build_adv_frame, build_training_frame


def _rows(paths: list[str]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        season = Path(p).stem.split("_")[0]
        try:
            rows += normalize_merged_gw(p, season=season)
        except Exception:  # sample CSV is already in normalized shape
            rows += pd.read_csv(p).assign(season=season).to_dict("records")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", nargs="+", required=True)
    ap.add_argument("--out", default=f"docs/xp-backtest/adv-{dt.date.today():%Y-%m-%d}.md")
    ap.add_argument("--min-train-gw", type=int, default=5)
    ap.add_argument("--n-estimators", type=int, default=60)
    ap.add_argument("--learning-rate", type=float, default=0.07)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--gw-stride", type=int, default=3)
    args = ap.parse_args()

    rows = _rows(args.csv)
    adv_frame = build_adv_frame(rows)
    basic_frame = build_training_frame(rows)

    adv = walk_forward_adv(
        adv_frame, min_train_gw=args.min_train_gw, gw_stride=args.gw_stride,
        n_estimators=args.n_estimators, learning_rate=args.learning_rate,
        max_depth=args.max_depth,
    ).metrics_by_position()
    basic = walk_forward(basic_frame, min_train_gw=args.min_train_gw,
                         gw_stride=args.gw_stride).metrics_by_position()

    positions = sorted(set(adv) | set(basic))
    wins = sum(
        1 for p in positions
        if p in adv and p in basic and adv[p]["rmse"] <= basic[p]["rmse"]
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Advanced xP backtest - {dt.date.today():%Y-%m-%d}",
        "",
        f"- adv rows: {len(adv_frame)} | basic rows: {len(basic_frame)}",
        f"- GBRT: n_estimators={args.n_estimators} lr={args.learning_rate} "
        f"max_depth={args.max_depth}",
        f"- **adv beats/ties basic on RMSE: {wins}/{len(positions)} positions** "
        f"(M3 needs >= 3/4)",
        "",
        "| position | n | basic RMSE | adv RMSE | adv MAE | baseline RMSE | adv wins |",
        "|---|---:|---:|---:|---:|---:|:--:|",
    ]
    for p in positions:
        a = adv.get(p, {})
        b = basic.get(p, {})
        win = "yes" if a and b and a["rmse"] <= b["rmse"] else "no"
        lines.append(
            f"| {p} | {a.get('n', 0)} | {b.get('rmse', float('nan')):.3f} | "
            f"{a.get('rmse', float('nan')):.3f} | {a.get('mae', float('nan')):.3f} | "
            f"{a.get('baseline_rmse', float('nan')):.3f} | {win} |"
        )
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out} (adv wins {wins}/{len(positions)})")


if __name__ == "__main__":
    main()
