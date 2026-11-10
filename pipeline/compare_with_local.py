"""Rebuilds the 17 features from Athena's tables and compares them with the local table."""
import sys
from pathlib import Path

import duckdb
import pandas as pd

BANDS = {"00-07": "00_07", "07-10": "07_10", "10-16": "10_16", "16-20": "16_20", "20-24": "20_24"}
TOLERANCE = 1e-9
ROOT = Path(__file__).resolve().parent.parent


def rebuild(work):
    bands = pd.read_csv(work / "band_counts.csv")
    totals = pd.read_csv(work / "station_window_totals.csv")
    bands["band"] = bands.band.map(BANDS)
    index = ["win", "location_id"]
    check_in = bands.pivot(index=index, columns="band", values="check_ins").fillna(0)
    check_out = bands.pivot(index=index, columns="band", values="check_outs").fillna(0)

    totals["volume_share"] = totals.timed_taps / totals.groupby("win").timed_taps.transform("sum")
    totals["weekend_share"] = totals.weekend_taps / totals.timed_taps
    kept = totals[totals.passes_minimum].set_index(index)
    return kept[["timed_taps", "check_ins", "check_outs", "weekend_share", "volume_share"]].join([
        check_in.div(check_in.sum(axis=1), axis=0).add_prefix("check_in_share_"),
        check_out.div(check_out.sum(axis=1), axis=0).add_prefix("check_out_share_"),
        ((check_in - check_out) / (check_in + check_out)).add_prefix("net_flow_")])


def main():
    aws = rebuild(Path(sys.argv[1]))
    local_path = (ROOT / "results" / "features" / "features_unscaled.parquet").as_posix()
    local = duckdb.connect().execute(f"select * from '{local_path}'").df()
    local = local.drop(columns="station").set_index(["win", "location_id"])

    same_rows = set(aws.index) == set(local.index)
    print(f"Rows: AWS {len(aws)}, local {len(local)}, same station-windows: {same_rows}")
    aws = aws.reindex(local.index)[local.columns]
    gaps = (aws - local).abs().max().sort_values(ascending=False)
    print(f"Columns compared: {len(gaps)}, largest gap: {gaps.iloc[0]:.2e} ({gaps.index[0]})")
    if not same_rows or aws.isna().any().any() or gaps.iloc[0] > TOLERANCE:
        sys.exit("FAIL: AWS and local tables differ.")
    print("PASS: AWS reproduces the local feature table.")


if __name__ == "__main__":
    main()
