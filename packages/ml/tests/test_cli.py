import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SAMPLE = REPO / "packages/ml/tests/fixtures/history_sample.csv"


def test_train_cli_writes_artifacts(tmp_path):
    out = tmp_path / "model"
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts/train_xp.py"),
         "--csv", str(SAMPLE), "--out", str(out)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert r.returncode == 0, r.stderr
    assert (out / "meta.json").exists()
    from fplguru_ml.model_basic import BasicXP
    m = BasicXP.load(out)
    assert m.version == "basic-v1"


def test_backtest_cli_writes_report(tmp_path):
    rep = tmp_path / "bt.md"
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts/backtest_xp.py"),
         "--csv", str(SAMPLE), "--out", str(rep), "--min-train-gw", "1"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert r.returncode == 0, r.stderr
    body = rep.read_text().lower()
    assert "| position |" in body and "rmse" in body
