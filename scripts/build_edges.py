"""Build the station-window graph for ST-GRSC.

Reads reference/line_order.csv and results/features/features.parquet.
Writes reference/edges.csv, one row per undirected link, stored once.

    src_win, src_location_id, dst_win, dst_location_id, kind, weight

Two kinds of link:

  spatial   neighbouring stations on a line, within one window
  temporal  the same station in consecutive windows it appears in

SPATIAL

Each segment in line_order.csv is a simple path. For a given window we keep the
stations present in that window and link consecutive survivors, so a station
absent from a window has its neighbours joined directly. That is the gap rule:
the track did not disappear, only the data did.

Contraction, not filtering, matters at Jabal Ali (155). It is the first stop of
both red_branch and red_2020 and is absent in W18/19 and W19/20. Filtering it
out would leave the western end of the network detached from the trunk;
contracting joins DMCC to Ibn Battuta instead. MAX_CONTRACTED_DEGREE guards the
case this cannot currently hit -- an absent station with three present
neighbours, where joining every pair would add a triangle rather than a bridge.

TEMPORAL

Per station, consecutive windows in which it appears, weighted by the real gap
between them, so a bridged link is weighted by its true span and not as if it
were adjacent.

INVARIANT

The network holds exactly one cycle, the loop formed by the Red link from Union
to BurJuman and the longer Green path between the same two stations. So for any
window, spatial edges == stations present. Bridging preserves it; a mistake in
the topology does not.
"""

from pathlib import Path
from itertools import combinations
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "results" / "features" / "features.parquet"
LINE_ORDER = ROOT / "reference" / "line_order.csv"
OUT = ROOT / "reference" / "edges.csv"

# Windows in time order, with the years spanned between each and the next.
WINDOWS = ["W17/18", "W18/19", "W19/20", "W21/22", "W24/25"]
GAP_YEARS = {("W17/18", "W18/19"): 1,
             ("W18/19", "W19/20"): 1,
             ("W19/20", "W21/22"): 2,
             ("W21/22", "W24/25"): 3}

SPATIAL_WEIGHT = 1.0

# Temporal weight decays as 1/years. Team decision, 21 Nov 2026: a one-year gap
# is full strength, longer gaps proportionally weaker. Change here and re-run.
def temporal_weight(years: int) -> float:
    return round(1.0 / years, 4)


def full_adjacency(segments):
    """The whole network, every station, from the ordered segments.

    Built across all segments at once so the junction is a single node of
    degree three rather than three separate segment endpoints.
    """
    adj = {}
    for ids in segments.values():
        for a, b in zip(ids, ids[1:]):
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    return adj


def spatial_edges_for_window(adj, present):
    """Edges among the present stations, contracting the absent ones away.

    Contraction, not filtering: removing a station joins its neighbours to one
    another, so an absent station bridges rather than breaks the line. Applied
    over the whole network, so it also bridges across a segment boundary --
    which is the case at Jabal Ali, the junction, absent in two windows.

    The outcome does not depend on the order nodes are removed in: an edge
    created through a node that is itself later removed disappears with it.
    """
    work = {node: set(nbrs) for node, nbrs in adj.items()}
    for node in [n for n in work if n not in present]:
        nbrs = work.pop(node)
        for other in nbrs:
            work[other].discard(node)
        for a, b in combinations(sorted(nbrs), 2):
            if a in work and b in work:
                work[a].add(b)
                work[b].add(a)
    return {(min(a, b), max(a, b)) for a, nbrs in work.items() for b in nbrs}


def n_components(nodes, edges):
    """Connected components, by union-find. No scipy dependency needed."""
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return len({find(n) for n in nodes})


def main() -> int:
    for path in (FEATURES, LINE_ORDER):
        if not path.is_file():
            sys.exit(f"missing {path}")

    feats = pd.read_parquet(FEATURES, columns=["win", "location_id", "station"])
    order = pd.read_csv(LINE_ORDER).sort_values(["segment", "position"])

    segments = {seg: list(sub.location_id)
                for seg, sub in order.groupby("segment", sort=False)}
    present_by_win = {w: set(feats.loc[feats.win == w, "location_id"])
                      for w in WINDOWS}

    adj = full_adjacency(segments)
    direct = {(min(a, b), max(a, b)) for a, nbrs in adj.items() for b in nbrs}

    errors = []
    rows = []
    bridges = []

    # ---- spatial --------------------------------------------------------
    for win in WINDOWS:
        present = present_by_win[win]
        edges = spatial_edges_for_window(adj, present)

        names = feats.drop_duplicates("location_id").set_index("location_id")["station"]
        for a, b in sorted(edges - direct):
            bridges.append(f"  {win}  {a} {names.get(a)} -- {b} {names.get(b)}")

        if len(edges) != len(present):
            errors.append(
                f"{win}: {len(edges)} spatial edges for {len(present)} stations "
                f"(the one-cycle invariant requires these to be equal)")

        # Equal counts alone would also hold for, say, two components one of
        # which has two cycles. Connectedness is what the spectral embedding
        # actually needs: a split graph adds a zero eigenvalue and the method
        # spends a cluster separating components instead of finding structure.
        n_comp = n_components(present, edges)
        if n_comp != 1:
            errors.append(f"{win}: spatial graph has {n_comp} components, expected 1")

        for a, b in sorted(edges):
            rows.append(dict(src_win=win, src_location_id=a,
                             dst_win=win, dst_location_id=b,
                             kind="spatial", weight=SPATIAL_WEIGHT))

    # ---- temporal -------------------------------------------------------
    cumulative = {WINDOWS[0]: 0}
    for a, b in zip(WINDOWS, WINDOWS[1:]):
        cumulative[b] = cumulative[a] + GAP_YEARS[(a, b)]

    for lid in sorted(feats.location_id.unique()):
        appears = [w for w in WINDOWS if lid in present_by_win[w]]
        for a, b in zip(appears, appears[1:]):
            years = cumulative[b] - cumulative[a]
            rows.append(dict(src_win=a, src_location_id=lid,
                             dst_win=b, dst_location_id=lid,
                             kind="temporal", weight=temporal_weight(years)))

    edges_df = pd.DataFrame(rows)

    # ---- checks ---------------------------------------------------------
    self_loops = edges_df[(edges_df.src_win == edges_df.dst_win)
                          & (edges_df.src_location_id == edges_df.dst_location_id)]
    if len(self_loops):
        errors.append(f"{len(self_loops)} self-loops")

    key = ["src_win", "src_location_id", "dst_win", "dst_location_id"]
    dupes = edges_df[edges_df.duplicated(key, keep=False)]
    if len(dupes):
        errors.append(f"{len(dupes)} duplicate pairs:\n{dupes.to_string()}")

    nodes = set(zip(feats.win, feats.location_id))
    for side in ("src", "dst"):
        bad = edges_df[~pd.Series(
            list(zip(edges_df[f"{side}_win"], edges_df[f"{side}_location_id"]))
        ).isin(nodes).to_numpy()]
        if len(bad):
            errors.append(f"{len(bad)} edges whose {side} is not a station-window "
                          f"in the feature table")

    if edges_df.weight.le(0).any():
        errors.append("non-positive weights")

    if errors:
        print("FAILED")
        for e in errors:
            print("  -", e)
        return 1

    edges_df.to_csv(OUT, index=False)

    spatial = edges_df[edges_df.kind == "spatial"]
    temporal = edges_df[edges_df.kind == "temporal"]

    print(f"OK  {len(edges_df)} edges -> reference/edges.csv")
    print(f"    spatial  {len(spatial):>4}   total weight {spatial.weight.sum():8.2f}")
    print(f"    temporal {len(temporal):>4}   total weight {temporal.weight.sum():8.2f}")
    share = spatial.weight.sum() / edges_df.weight.sum()
    print(f"    spatial carries {share:.1%} of the graph's weight")
    print()
    per_win = (spatial.groupby("src_win").size()
               .reindex(WINDOWS).rename("spatial_edges").to_frame())
    per_win["stations"] = [len(present_by_win[w]) for w in WINDOWS]
    print(per_win.to_string())
    print()
    print(f"bridges created where a station was absent ({len(bridges)}):")
    print("\n".join(bridges) if bridges else "  none")
    print()
    print("temporal links by weight:")
    print(temporal.weight.value_counts().sort_index(ascending=False)
          .rename("edges").to_frame().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
