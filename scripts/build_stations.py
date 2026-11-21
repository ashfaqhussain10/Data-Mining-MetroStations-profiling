"""Build the station reference tables for the Dubai Metro graph.

Writes two files to reference/:

  stations.csv    one row per station (53), with its line and first window seen
  line_order.csv  the network topology as ordered sequences

line_order.csv is the important one. Each segment is a simple path, so every
spatial edge is just a consecutive pair within a segment -- no special cases in
the edge builder. Junction and interchange stations appear in more than one
segment, which is how the branch and the two line crossings are expressed:

  red          Centrepoint .. Jabal Ali          25 stations, the trunk
  red_branch   Jabal Ali .. UAE Exchange          5, repeats Jabal Ali
  red_2020     Jabal Ali .. EXPO                  7, repeats Jabal Ali
  green        Etisalat .. Creek                 20, repeats Union + BurJuman

Order verified against Wikipedia's Red Line and Green Line station tables,
November 2026. location_id runs in geographic sequence along each line, so the
sequences below are the sorted ids with three corrections:

  - 144, 145, 147, 180, 186 are unused ids, not missing stations
  - Union (135) and BurJuman (136) are Red/Green interchanges and so appear in
    the green sequence at the positions left empty by ids 169 and 175
  - Jabal Ali (155) is the junction where the line splits three ways
"""

from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "results" / "features" / "features.parquet"
DRAFT_MAP = ROOT / "results" / "profile" / "station_map_draft.csv"
OUT_DIR = ROOT / "reference"

SEGMENTS = {
    "red": [128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140,
            141, 142, 143, 146, 148, 149, 150, 151, 152, 153, 154, 155],
    "red_branch": [155, 156, 157, 158, 159],
    "red_2020": [155, 181, 182, 183, 184, 185, 187],
    "green": [160, 161, 162, 163, 164, 165, 166, 167, 168, 135, 170, 171, 172,
              173, 174, 136, 176, 177, 178, 179],
}

# Which line each station belongs to in stations.csv. Interchanges and the
# junction are listed once, under the line that owns their location_id block.
LINE_OF_SEGMENT = {
    "red": "Red",
    "red_branch": "Red",
    "red_2020": "Red",
    "green": "Green",
}


def main() -> int:
    if not FEATURES.is_file():
        sys.exit(f"missing {FEATURES} -- run the feature build first")

    feats = pd.read_parquet(FEATURES, columns=["win", "location_id", "station"])
    names = (feats.drop_duplicates("location_id")
                  .set_index("location_id")["station"].to_dict())
    first_win = feats.groupby("location_id")["win"].min().to_dict()

    draft = pd.read_csv(DRAFT_MAP).drop_duplicates("location_id")
    line_name = draft.set_index("location_id")["line_name"].to_dict()

    # ---- line_order.csv -------------------------------------------------
    rows = []
    for segment, ids in SEGMENTS.items():
        for position, lid in enumerate(ids, start=1):
            rows.append({
                "segment": segment,
                "position": position,
                "location_id": lid,
                "station": names.get(lid, "<UNKNOWN>"),
            })
    order = pd.DataFrame(rows)

    # ---- stations.csv ---------------------------------------------------
    primary = {}
    for segment, ids in SEGMENTS.items():
        for lid in ids:
            primary.setdefault(lid, segment)

    appears_in = order.groupby("location_id")["segment"].nunique()

    stations = pd.DataFrame({
        "location_id": sorted(primary),
    })
    stations["station"] = stations.location_id.map(names)
    stations["line"] = stations.location_id.map(
        lambda i: LINE_OF_SEGMENT[primary[i]])
    stations["line_name_raw"] = stations.location_id.map(line_name)
    stations["primary_segment"] = stations.location_id.map(primary)
    stations["is_junction_or_interchange"] = stations.location_id.map(
        lambda i: appears_in[i] > 1)
    stations["first_win"] = stations.location_id.map(first_win)

    # ---- checks ---------------------------------------------------------
    errors = []

    in_features = set(feats.location_id.unique())
    listed = set(stations.location_id)
    if listed != in_features:
        errors.append(
            f"station set mismatch: only in features {sorted(in_features - listed)}, "
            f"only in SEGMENTS {sorted(listed - in_features)}")

    if len(stations) != 53:
        errors.append(f"expected 53 stations, got {len(stations)}")

    unknown = stations[stations.station.isna()]
    if len(unknown):
        errors.append(f"no name for location_id {list(unknown.location_id)}")

    # Each segment must be a simple path with no repeats inside itself.
    for segment, ids in SEGMENTS.items():
        if len(ids) != len(set(ids)):
            errors.append(f"segment {segment} repeats a station")

    # Expected multi-segment members, and nothing else.
    multi = set(appears_in[appears_in > 1].index)
    if multi != {135, 136, 155}:
        errors.append(f"expected 135/136/155 in several segments, got {sorted(multi)}")

    # Edge count the topology implies, against stations present per window.
    # The network has exactly one cycle (the Union-BurJuman loop), so for a
    # fully-present window: edges == nodes.
    total_edges = sum(len(ids) - 1 for ids in SEGMENTS.values())
    if total_edges != 53:
        errors.append(f"topology implies {total_edges} spatial edges, expected 53")

    if errors:
        print("FAILED")
        for e in errors:
            print("  -", e)
        return 1

    OUT_DIR.mkdir(exist_ok=True)
    stations.to_csv(OUT_DIR / "stations.csv", index=False)
    order.to_csv(OUT_DIR / "line_order.csv", index=False)

    print(f"OK  {len(stations)} stations -> reference/stations.csv")
    print(f"OK  {len(order)} ordered positions over {len(SEGMENTS)} segments "
          f"-> reference/line_order.csv")
    print(f"    full-network spatial edges implied: {total_edges}")
    print()
    print(stations.groupby(["line", "primary_segment"]).size().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
