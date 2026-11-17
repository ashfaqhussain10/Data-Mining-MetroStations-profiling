"""Labels every station from OpenStreetMap features around it, as an outside check on the clusters.

Usage:
    python src/landuse_labels.py            # fetch counts (cached) and label
    python src/landuse_labels.py --refetch  # ignore the cache and query OpenStreetMap again

Rules (agreed with the team):
  1. Airport: an airport terminal within AIRPORT_RADIUS_M.
  2. Transfer and hub: a Red/Green interchange (BurJuman, Union).
  3. Otherwise count features within RADIUS_M in four groups (Business, Residential,
     Shopping and leisure, Education). Take each group's share at the station, divide by
     that group's average share across all stations, and pick the group with the highest
     ratio if it is at least THRESHOLD. Education can only win with MIN_SCHOOLS or more.
  4. Mixed when no group reaches THRESHOLD.

Revision on 17 Nov 2026 (v2), after the first run agreed with only 5 of 12 hand labels:
  - Bus or ferry stations no longer make a hub: feeder bus stops at most metro stations are
    tagged as bus stations, which turned 13 of 53 stations into hubs.
  - Education needs at least MIN_SCHOOLS schools: with only 327 schools mapped, one or two
    schools pushed a station to 3-5x the average share.
  The first run is kept as results/landuse/*_v1_original.csv.

Features are fetched once per group for the whole metro area (6 requests, cached in
data/osm/, git-ignored), then counted around each station locally.

Writes results/landuse/osm_counts.csv (raw counts) and results/landuse/landuse_labels.csv.
"""
import json
import math
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
import pandas as pd

# certifi's certificate list is newer than some Windows Python installs, which reject
# the current Let's Encrypt chain used by the OpenStreetMap servers.
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

ROOT = Path(__file__).resolve().parent.parent
STATIONS_FILE = next((ROOT / "data" / "raw").glob("metro_stations_*.csv"), None)
STATION_MAP = ROOT / "results" / "profile" / "station_map_draft.csv"
HAND_LABELS = ROOT / "results" / "hand_labels.csv"
OUT_DIR = ROOT / "results" / "landuse"
COUNTS_FILE = OUT_DIR / "osm_counts.csv"
POINTS_DIR = ROOT / "data" / "osm"

RADIUS_M = 1000
AIRPORT_RADIUS_M = 500
HUB_RADIUS_M = 300
THRESHOLD = 1.3
MIN_SCHOOLS = 5  # Education can only win with at least this many schools within RADIUS_M
INTERCHANGES = {"BurJuman", "Union"}
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
PAUSE_SECONDS = 5
# South, west, north, east: every station plus a 1 km margin.
BBOX = (24.94, 55.07, 25.30, 55.42)

GROUPS = {
    "business": ['nwr["office"]', 'nwr["building"~"^(office|commercial)$"]'],
    "residential": ['nwr["building"~"^(residential|apartments|house|detached|terrace|villa|dormitory)$"]'],
    "shopping_leisure": ['nwr["shop"]',
                         'nwr["tourism"~"^(hotel|hostel|guest_house|attraction|museum|gallery|theme_park)$"]',
                         'nwr["leisure"~"^(park|stadium|sports_centre|water_park|fitness_centre)$"]'],
    "education": ['nwr["amenity"~"^(school|kindergarten|college|university)$"]'],
    "airport_terminal": ['nwr["aeroway"="terminal"]'],
    "bus_or_ferry": ['nwr["amenity"~"^(bus_station|ferry_terminal)$"]'],
}
GROUP_RADIUS = {"airport_terminal": AIRPORT_RADIUS_M, "bus_or_ferry": HUB_RADIUS_M}
TYPE_NAMES = {"business": "Business", "residential": "Residential",
              "shopping_leisure": "Shopping and leisure", "education": "Education"}


def load_stations():
    if STATIONS_FILE is None:
        sys.exit("data/raw/metro_stations_*.csv not found.")
    coords = pd.read_csv(STATIONS_FILE, dtype=str)
    coords["location_id"] = coords.location_id.astype(int)
    names = pd.read_csv(STATION_MAP)[["location_id", "station"]].drop_duplicates("location_id")
    stations = names.merge(coords[["location_id", "station_location_latitude", "station_location_longitude"]],
                           on="location_id", how="left")
    stations = stations.rename(columns={"station_location_latitude": "lat", "station_location_longitude": "lon"})
    assert stations.lat.notna().all(), stations[stations.lat.isna()]
    return stations.sort_values("location_id").reset_index(drop=True)


def fetch_group(group):
    """All features of one group in the metro area, as (lat, lon) points; cached on disk."""
    cache = POINTS_DIR / f"{group}.csv"
    if cache.exists():
        return pd.read_csv(cache)
    south, west, north, east = BBOX
    union = "".join(c + ";" for c in GROUPS[group])
    query = f"[out:json][timeout:600][bbox:{south},{west},{north},{east}];({union});out center qt;"
    data = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": "dubai-metro-station-profiling"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=900, context=SSL_CONTEXT) as response:
                elements = json.loads(response.read())["elements"]
            break
        except Exception as error:  # busy server or timeout: wait and retry
            wait = 30 * (attempt + 1)
            print(f"  {group}: retry in {wait}s ({error})", flush=True)
            time.sleep(wait)
    else:
        raise SystemExit(f"OpenStreetMap did not return {group} after 4 attempts.")
    points = pd.DataFrame(
        [(e.get("lat", e.get("center", {}).get("lat")), e.get("lon", e.get("center", {}).get("lon"))) for e in elements],
        columns=["lat", "lon"]).dropna()
    POINTS_DIR.mkdir(parents=True, exist_ok=True)
    points.to_csv(cache, index=False)
    print(f"  {group}: {len(points):,} features", flush=True)
    time.sleep(PAUSE_SECONDS)
    return points


def distances_m(lat, lon, points):
    """Great-circle distance in metres from one station to every point."""
    p1, p2 = math.radians(lat), points.lat.map(math.radians)
    dlat = p2 - p1
    dlon = (points.lon - lon).map(math.radians)
    a = (dlat / 2).map(math.sin) ** 2 + math.cos(p1) * p2.map(math.cos) * (dlon / 2).map(math.sin) ** 2
    return 2 * 6371000 * a.map(lambda v: math.asin(math.sqrt(v)))


def fetch_all(stations, refetch):
    if refetch and POINTS_DIR.exists():
        for f in POINTS_DIR.glob("*.csv"):
            f.unlink()
    points = {group: fetch_group(group) for group in GROUPS}
    rows = []
    for _, s in stations.iterrows():
        lat, lon = float(s.lat), float(s.lon)
        counts = {g: int((distances_m(lat, lon, pts) <= GROUP_RADIUS.get(g, RADIUS_M)).sum()) for g, pts in points.items()}
        rows.append({"location_id": s.location_id, "station": s.station, "lat": lat, "lon": lon, **counts})
    counts = pd.DataFrame(rows).sort_values("location_id").reset_index(drop=True)
    counts.to_csv(COUNTS_FILE, index=False)
    return counts


def label(counts):
    groups = list(TYPE_NAMES)
    totals = counts[groups].sum(axis=1).replace(0, float("nan"))
    shares = counts[groups].div(totals, axis=0)
    ratios = shares / shares.mean()
    result = counts[["location_id", "station"]].copy()
    for g in groups:
        result[f"{g}_ratio"] = ratios[g].round(3)
    eligible = ratios.copy()
    eligible.loc[counts.education < MIN_SCHOOLS, "education"] = float("-inf")
    result["top_group"] = eligible.idxmax(axis=1)
    result["top_ratio"] = eligible.max(axis=1).round(3)

    def decide(i):
        row = counts.loc[i]
        if row.airport_terminal > 0:
            return "Airport", f"airport terminal within {AIRPORT_RADIUS_M} m"
        if row.station in INTERCHANGES:
            return "Transfer and hub", "Red/Green interchange"
        if result.loc[i, "top_ratio"] >= THRESHOLD:
            g = result.loc[i, "top_group"]
            return TYPE_NAMES[g], f"{TYPE_NAMES[g]} share {result.loc[i, 'top_ratio']}x the average"
        return "Mixed", f"no group reaches {THRESHOLD}x the average"

    decided = [decide(i) for i in counts.index]
    result["landuse_type"] = [d[0] for d in decided]
    result["rule"] = [d[1] for d in decided]
    return result


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stations = load_stations()
    counts = fetch_all(stations, "--refetch" in sys.argv)
    labels = label(counts)
    labels.to_csv(OUT_DIR / "landuse_labels.csv", index=False)
    print(f"\n{len(labels)} stations labelled; radius {RADIUS_M} m, threshold {THRESHOLD}x")
    print(labels.landuse_type.value_counts().to_string())

    if HAND_LABELS.exists():
        hand = pd.read_csv(HAND_LABELS)[["location_id", "station", "expected_type"]]
        both = hand.merge(labels[["location_id", "landuse_type", "rule"]], on="location_id")
        both["agree"] = both.expected_type == both.landuse_type
        both.to_csv(OUT_DIR / "agreement_with_hand_labels.csv", index=False)
        print(f"\nAgreement with hand labels: {int(both.agree.sum())} of {len(both)}")
        print(both[["station", "expected_type", "landuse_type", "agree"]].to_string(index=False))


if __name__ == "__main__":
    main()
