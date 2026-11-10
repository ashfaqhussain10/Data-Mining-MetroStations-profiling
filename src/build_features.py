"""Build the station-window feature table from the raw ridership parts.

Usage:
    python src/build_features.py

Reads data/raw/ and results/profile/station_map_draft.csv.
Writes to results/features/:
    features.parquet           244 rows, 17 z-scored features plus keys
    features_unscaled.parquet  the same rows before z-scoring
    removed.csv                station-windows below the minimum tap count
    feature_summary.csv        mean and standard deviation of each feature

Rows that look identical are kept. They appear to be different passengers
tapping in the same second, so they are not de-duplicated.
"""
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATION_MAP = ROOT / "results" / "profile" / "station_map_draft.csv"
OUT_DIR = ROOT / "results" / "features"

WINDOWS = [("W17/18", "2017-11", "2018-02"), ("W18/19", "2018-09", "2019-02"),
           ("W19/20", "2019-09", "2020-02"), ("W21/22", "2021-09", "2022-02"),
           ("W24/25", "2024-09", "2025-02")]
BANDS = [("00_07", 0, 7), ("07_10", 7, 10), ("10_16", 10, 16), ("16_20", 16, 20), ("20_24", 20, 24)]
MIN_TAPS = 300
EXPECTED_ROWS = 244


def load_taps(con):
    """Timed taps inside the windows, mapped to stations and bands."""
    files = sorted(RAW_DIR.glob("metro_ridership_*.csv"))
    paths = ",".join(f"'{path.as_posix()}'" for path in files)
    windows = " ".join(f"when substr(txn_date, 1, 7) between '{a}' and '{b}' then '{name}'"
                       for name, a, b in WINDOWS)
    bands = " ".join(f"when hr >= {low} and hr < {high} then '{name}'" for name, low, high in BANDS)

    con.execute(f"""
    create table station_map as
    select raw_name, nullif(line_name, '') as line_name, cast(location_id as int) as location_id, station
    from read_csv('{STATION_MAP.as_posix()}', all_varchar=true, header=true)""")
    con.execute("""
    create table name_only as
    select raw_name, min(location_id) as location_id, min(station) as station
    from station_map group by 1 having count(distinct location_id) = 1""")
    con.execute(f"""
    create table timed as
    select *, case {bands} end as band
    from (
        select regexp_replace(trim(replace(end_location, ' Metro Station', '')), '\\s+', ' ', 'g') as raw_name,
               line_name, txn_type, cast(txn_date as date) as dt,
               cast(substr(txn_time, 1, 2) as int) as hr,
               case {windows} end as win
        from read_csv([{paths}], all_varchar=true, header=true, quote='"')
        where end_location is not null and not starts_with(txn_time, '00:00:00'))
    where win is not null""")
    con.execute("""
    create table taps as
    select t.win, t.band, t.txn_type = 'Check in' as is_check_in,
           coalesce(m.location_id, f.location_id) as location_id,
           coalesce(m.station, f.station) as station,
           case when t.dt < date '2022-01-01' then dayname(t.dt) in ('Friday', 'Saturday')
                else dayname(t.dt) in ('Saturday', 'Sunday') end as is_weekend
    from timed t
    left join station_map m on t.raw_name = m.raw_name and t.line_name is not distinct from m.line_name
    left join name_only f on t.raw_name = f.raw_name""")
    missing = con.execute("select count(*) from taps where location_id is null").fetchone()[0]
    if missing:
        raise SystemExit(f"{missing} taps have no station mapping.")
    return len(files)


def build_table(con):
    totals = con.execute("""
    select win, location_id, station, count(*) as timed_taps,
           sum(is_check_in::int) as check_ins, sum((not is_check_in)::int) as check_outs,
           avg(is_weekend::int) as weekend_share
    from taps group by 1, 2, 3""").df()
    totals["volume_share"] = totals.timed_taps / totals.groupby("win").timed_taps.transform("sum")

    cells = con.execute("""
    select win, location_id, band, sum(is_check_in::int) as ci, sum((not is_check_in)::int) as co
    from taps group by 1, 2, 3""").df()
    names = [name for name, _, _ in BANDS]
    check_in = cells.pivot(index=["win", "location_id"], columns="band", values="ci").reindex(columns=names).fillna(0)
    check_out = cells.pivot(index=["win", "location_id"], columns="band", values="co").reindex(columns=names).fillna(0)

    shares_in = check_in.div(check_in.sum(axis=1), axis=0).add_prefix("check_in_share_")
    shares_out = check_out.div(check_out.sum(axis=1), axis=0).add_prefix("check_out_share_")
    net_flow = ((check_in - check_out) / (check_in + check_out)).add_prefix("net_flow_")

    table = totals.set_index(["win", "location_id"]).join([shares_in, shares_out, net_flow]).reset_index()
    return table.sort_values(["location_id", "win"]).reset_index(drop=True)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    n_files = load_taps(con)
    table = build_table(con)

    keys = ["win", "location_id", "station", "timed_taps", "check_ins", "check_outs"]
    features = [c for c in table.columns if c.startswith(("check_in_share", "check_out_share", "net_flow"))]
    features += ["weekend_share", "volume_share"]

    removed = table[table.timed_taps < MIN_TAPS][keys]
    kept = table[table.timed_taps >= MIN_TAPS].reset_index(drop=True)[keys + features]
    assert len(features) == 17 and len(kept) == EXPECTED_ROWS, (len(features), len(kept))
    assert not kept[features].isna().any().any(), "A feature is empty."

    summary = kept[features].agg(["mean", "std"]).T.reset_index(names="feature")
    scaled = kept.copy()
    scaled[features] = (kept[features] - kept[features].mean()) / kept[features].std(ddof=0)

    con.register("unscaled", kept)
    con.register("scaled", scaled)
    con.execute(f"copy unscaled to '{(OUT_DIR / 'features_unscaled.parquet').as_posix()}' (format parquet)")
    con.execute(f"copy scaled to '{(OUT_DIR / 'features.parquet').as_posix()}' (format parquet)")
    removed.to_csv(OUT_DIR / "removed.csv", index=False)
    summary.to_csv(OUT_DIR / "feature_summary.csv", index=False)
    print(f"{n_files} parts, {int(table.timed_taps.sum()):,} taps, {len(table)} station-windows, "
          f"{len(kept)} kept, {len(removed)} removed, {len(features)} features")


if __name__ == "__main__":
    main()
