"""Turns Athena's feature tables (downloaded as CSV) into the files the models read.

Usage: python pipeline/export_features.py <folder holding features.csv, features_unscaled.csv, removed.csv>

Writes to results/features/:
    features.parquet           model input: keys plus 17 z-scored features
    features_unscaled.parquet  the same rows before scaling
    removed.csv                station-windows below the 300-tap minimum
    feature_summary.csv        mean and standard deviation of each feature

If local copies already exist, the new values must match them to within 1e-9,
otherwise nothing is overwritten. Use --replace to overwrite anyway.
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "features"
KEYS = ["win", "location_id", "station", "timed_taps", "check_ins", "check_outs"]
BANDS = ["00_07", "07_10", "10_16", "16_20", "20_24"]
FEATURES = ([f"check_in_share_{b}" for b in BANDS] + [f"check_out_share_{b}" for b in BANDS]
            + [f"net_flow_{b}" for b in BANDS] + ["weekend_share", "volume_share"])
TOLERANCE = 1e-9


def load(path):
    table = pd.read_csv(path)
    for column in ["location_id", "timed_taps", "check_ins", "check_outs"]:
        table[column] = table[column].astype("int64")
    return table[KEYS + FEATURES].sort_values(["location_id", "win"]).reset_index(drop=True)


def largest_gap(new, old_path):
    con = duckdb.connect()
    old = con.execute(f"select * from '{old_path.as_posix()}'").df()
    old = old[KEYS + FEATURES].sort_values(["location_id", "win"]).reset_index(drop=True)
    if len(old) != len(new) or not (old[["win", "location_id"]].values == new[["win", "location_id"]].values).all():
        return float("inf")
    return float((new[FEATURES] - old[FEATURES]).abs().max().max())


def main():
    folder = Path(sys.argv[1])
    replace = "--replace" in sys.argv
    scaled = load(folder / "features.csv")
    unscaled = load(folder / "features_unscaled.csv")
    removed = pd.read_csv(folder / "removed.csv")
    assert len(scaled) == len(unscaled) and len(FEATURES) == 17

    print(f"Athena features: {len(scaled)} rows, {len(FEATURES)} features, {len(removed)} removed")
    for name, table in (("features.parquet", scaled), ("features_unscaled.parquet", unscaled)):
        existing = OUT_DIR / name
        if existing.exists():
            gap = largest_gap(table, existing)
            print(f"  {name}: largest difference from current file {gap:.2e}")
            if gap > TOLERANCE and not replace:
                sys.exit("Athena output differs from the current files. Nothing was overwritten.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for name, table in (("features.parquet", scaled), ("features_unscaled.parquet", unscaled)):
        con.register("t", table)
        con.execute(f"copy t to '{(OUT_DIR / name).as_posix()}' (format parquet)")
        con.unregister("t")
    removed.to_csv(OUT_DIR / "removed.csv", index=False)
    unscaled[FEATURES].agg(["mean", "std"]).T.reset_index(names="feature").to_csv(
        OUT_DIR / "feature_summary.csv", index=False)
    print(f"Written to {OUT_DIR}")


if __name__ == "__main__":
    main()
