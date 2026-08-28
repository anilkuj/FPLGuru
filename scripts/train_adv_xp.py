"""Train the Advanced xP model (GBRT + quantile bands) from vaastav merged_gw CSV(s).

    python scripts/train_adv_xp.py --csv data/historical/2023-24_merged_gw.csv \\
        data/historical/2024-25_merged_gw.csv --out packages/ml/artifacts/advanced
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from fplguru_ingest.historical import normalize_merged_gw
from fplguru_ml.frame import build_adv_frame
from fplguru_ml.model_advanced import train_advanced


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
    ap.add_argument("--out", default="packages/ml/artifacts/advanced")
    ap.add_argument("--n-estimators", type=int, default=250)
    ap.add_argument("--learning-rate", type=float, default=0.05)
    ap.add_argument("--max-depth", type=int, default=3)
    args = ap.parse_args()

    frame = build_adv_frame(_rows(args.csv))
    model = train_advanced(
        frame, n_estimators=args.n_estimators,
        learning_rate=args.learning_rate, max_depth=args.max_depth,
    )
    model.save(args.out)
    print(f"trained {model.version}: positions={model.positions()} "
          f"rows={len(frame)} -> {args.out}")


if __name__ == "__main__":
    main()
