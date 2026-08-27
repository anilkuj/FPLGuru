"""Download vaastav/Fantasy-Premier-League merged_gw.csv for the given seasons.

Usage: python scripts/fetch_historical.py 2022-23 2023-24 2024-25
"""
import sys
from pathlib import Path
from urllib.request import urlretrieve

RAW = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/gws/merged_gw.csv"
DEST = Path("data/historical")


def main(seasons: list[str]) -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for season in seasons:
        target = DEST / f"{season}_merged_gw.csv"
        print(f"-> {target}")
        urlretrieve(RAW.format(season=season), target)


if __name__ == "__main__":
    main(sys.argv[1:] or ["2022-23", "2023-24", "2024-25"])
