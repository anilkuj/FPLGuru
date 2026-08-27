"""Walk-forward backtest of the Basic xP model; writes a Markdown report."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from fplguru_ingest.historical import normalize_merged_gw
from fplguru_ml.backtest import walk_forward
from fplguru_ml.frame import build_training_frame


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
    ap.add_argument("--out", default=f"docs/xp-backtest/{dt.date.today():%Y-%m-%d}.md")
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--min-train-gw", type=int, default=5)
    args = ap.parse_args()

    frame = build_training_frame(_rows(args.csv))
    res = walk_forward(frame, alpha=args.alpha, min_train_gw=args.min_train_gw)
    m = res.metrics_by_position()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Basic xP backtest - {dt.date.today():%Y-%m-%d}",
        "",
        f"- rows: {len(frame)} | folds: {len(res.folds)} | alpha: {args.alpha}",
        "",
        "| position | n | MAE | RMSE | baseline RMSE | beats baseline |",
        "|---|---:|---:|---:|---:|:--:|",
    ]
    for pos in sorted(m):
        r = m[pos]
        beats = "yes" if r["rmse"] < r["baseline_rmse"] else "no"
        lines.append(
            f"| {pos} | {r['n']} | {r['mae']:.3f} | {r['rmse']:.3f} | "
            f"{r['baseline_rmse']:.3f} | {beats} |"
        )
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
