# Dubai Metro Station Profiling

Clusters Dubai Metro stations by how passengers use them, and tracks how each station's type changes over time. The proposed method is **ST-GRSC** (spatio-temporal graph-regularised spectral clustering), compared against K-means, Ward, DBSCAN and plain spectral clustering.

BITS Pilani Dubai, CS F415 Data Mining, Semester I 2026-27. Team: Chaitanya Narkedamilly, Syed Ashfaque Hussain, Pokala Aryan Chandra.

## Status

| Stage | State |
|---|---|
| Dataset analysis | Done: `notebooks/01_dataset_profile.ipynb`, `notebooks/02_ten_parts_profile.ipynb` |
| Raw data, 10 parts (10.5 million rows) | Done: local `data/raw/` and S3 |
| AWS pipeline (S3, Glue, Athena) | Done, and matches the local results exactly |
| Feature table (244 rows x 17 features) | Done: `results/features/features.parquet` |
| Station graph (`edges.csv`) | Not started. Waits on station order and the link-weight decision |
| Five clustering methods and evaluation | Not started. Waits on hand labels |

## Repository layout

```
.
├── README.md
├── requirements.txt            Python packages for the notebooks and scripts
├── .gitignore                  keeps data/ and infra/config.local.sh out of git
├── data/                       NOT in git
│   └── raw/                    raw CSVs (ridership parts, stations, lines, official summary)
├── notebooks/
│   ├── 01_dataset_profile.ipynb    analysis of the first part only (1.05M rows)
│   └── 02_ten_parts_profile.ipynb  the same analysis on all 10 parts
├── src/
│   └── build_features.py       builds the 244 x 17 feature table from data/raw/
├── scripts/
│   └── download_parts.py       downloads chosen parts from data.dubai into data/raw/
├── sql/                        Athena SQL, run in order by pipeline/run_all.sh
│   ├── 01_external_tables.sql
│   ├── 02_curated_ridership.sql
│   ├── 03_band_counts.sql
│   ├── 04_station_window_totals.sql
│   └── 05_row_audit.sql
├── pipeline/
│   ├── upload_raw.sh           copies data/raw/ to S3 (project owner only)
│   ├── run_all.sh              rebuilds every curated table, then runs verify.sh
│   ├── verify.sh               10 checks against the notebook numbers
│   ├── athena.sh               helper: run a query, wait, fail on error
│   └── compare_with_local.*    rebuilds the features from Athena and compares with local
├── infra/                      AWS setup (project owner only)
│   ├── config.sh               shared names: bucket, region, workgroup, role
│   ├── config.local.example.sh template for config.local.sh (git-ignored)
│   ├── 01_create_resources.sh  bucket, Glue database, Athena workgroup, budget
│   ├── 02_team_access.sh       team role and IAM users
│   ├── 99_teardown.sh          deletes the AWS resources
│   ├── team_policy.json        what the team role may do
│   └── user_self_service_policy.json
├── results/
│   ├── profile/                tables from notebook 01, plus the draft station map
│   ├── profile_10parts/        tables from notebook 02
│   └── features/               the feature table handed to the models
├── figures/                    charts from the notebooks
└── docs/
    └── TEAM_SETUP.md           AWS sign-in and pipeline steps for teammates
```

## Data

**Source:** [Dubai Metro Ridership](https://data.dubai/en/l/466403), Roads and Transport Authority, published on Data Dubai under the Dubai Open Data Licence (attribution required, no resale).

The full export is 3,134 parts of about 147 MB each (about 484 GB, about 3.3 billion rows), named `metro_ridership_2026-07-21_18-21-58_NNNN.csv`. We use **10 parts spread across the list**, because neighbouring parts share many identical rows while distant parts share almost none:

`0001, 0002, 0300, 0586, 0900, 1186, 1500, 1786, 2100, 2386`

Other files in `data/raw/`:

| File | Rows | Use |
|---|---|---|
| `metro_stations_*.csv` | 55 | station IDs, lines, coordinates, opening dates |
| `metro_lines_*.csv` | 2 | Red and Green line names |
| `Number_of_Metro_Ridership_by_Lines_2026-11-05.csv` | 3,518 unique | official monthly riders per station, 2021 to 2026, used only to validate the sample |

### What one ridership row is

One card tap at one station gate. It is a sample, not every rider, and it is not a trip: start and end station are almost always the same, so there is no origin-destination information.

| Column | Example | Meaning |
|---|---|---|
| `end_location` | Business Bay Metro Station | station where the tap happened (the column we use) |
| `start_location` | Business Bay Metro Station | usually the same station, or empty |
| `end_zone`, `start_zone` | Zone 6 | fare zone |
| `line_name` | Red Metro Line | metro line |
| `txn_date` | 2024-10-21 | date of the tap |
| `txn_time` | 17:13:00.000 | time of the tap, or `00:00:00` when the time is missing |
| `txn_type` | Check in | Check in or Check out |
| `load_timestamp` | 2024-11-05T19:09:51Z | when the portal loaded the row (about 14 days after the tap) |

## Data pipeline

The same logic runs in two places, and both give identical results:

- **AWS** (the project pipeline): S3 + Glue Data Catalog + Athena, in `ap-south-1`.
- **Local** (analysis and checking): DuckDB in the notebooks and `src/build_features.py`.

```
data.dubai parts ──download_parts.py──> data/raw/ ──upload_raw.sh──> S3 raw/ (plain CSV)
                                           │                              │
                                           │                     Athena external tables
                                           │                              │
                                  build_features.py            curated_ridership (Parquet,
                                           │                   partitioned by year/month)
                                           │                              │
                                           │                 band_counts, station_window_totals,
                                           │                             row_audit
                                           ▼                              │
                        results/features/features.parquet <── compare_with_local (identical)
```

### Cleaning rules, in order

| Step | Rule | Rows left |
|---|---|---|
| Raw rows, 10 parts | | 10,484,655 |
| 1 | Drop rows with no station (`end_location` empty) | 10,475,284 |
| 2 | Drop date-only rows (`txn_time` is `00:00:00`); time-of-day features need a real time | 4,630,593 |
| 3 | Keep rows inside the five study windows | 3,340,959 |
| 4 | Group into station-windows | 245 |
| 5 | Keep station-windows with at least 300 timed taps | **244** |

Decisions behind these rules:

- **Tap station:** `end_location` for every row. It is filled on all but 942 rows of the first part; `start_location` is missing on about 10% of check-ins.
- **Station names:** 69 raw names map to 53 physical stations through `results/profile/station_map_draft.csv`, keyed on (raw name, line) to the stations file `location_id`. `Sharaf DG` is two stations: Red line is today's Mashreq, Green line is the former Al Fahidi. The renames are inferred from the dates each name appears and still need checking against RTA. BurJuman and Union are recorded only under the Red line, so each is one station.
- **Study windows:** tap times exist only in blocks of months (2023 has none), so calendar years would compare different seasons. We use five September-to-February windows: W17/18 (Nov-Feb), W18/19, W19/20, W21/22, W24/25. These also avoid a data format change in June 2025.
- **No de-duplication:** identical timed rows look like different passengers tapping in the same second (twice as common on check-outs, peaking at rush hour), so all rows are kept.
- **Weekend rule:** Friday and Saturday up to 31 Dec 2021, Saturday and Sunday from 1 Jan 2022.

### S3 layout

```
s3://dubai-metro-profiling-<account-id>/
├── raw/ridership/          10 ridership CSVs (never changed)
├── raw/stations/           stations CSV
├── raw/lines/              lines CSV
├── reference/station_map/  draft station map
├── curated/ridership/      year=YYYY/month=MM/ Parquet
├── curated/band_counts/
├── curated/station_window_totals/
├── curated/row_audit/
└── athena-results/         query results
```

### Athena tables (Glue database `dubai_metro`)

| Table | Made by | One row is | Main columns |
|---|---|---|---|
| `raw_ridership`, `raw_stations`, `raw_lines` | `01_external_tables.sql` | a CSV row, all text | the CSV columns |
| `ref_station_map` | `01_external_tables.sql` | a (raw name, line) pair | `raw_name`, `line_name`, `location_id`, `station` |
| `curated_ridership` | `02_curated_ridership.sql` | one tap with a station, including date-only taps | `source_file`, `txn_date`, `txn_type`, `is_check_in`, `location_id`, `station`, `date_only`, `hour_of_day`, `band`, `win`, `is_weekend`, partitions `year`, `month` |
| `band_counts` | `03_band_counts.sql` | station-window-band | `win`, `location_id`, `station`, `band`, `check_ins`, `check_outs` |
| `station_window_totals` | `04_station_window_totals.sql` | station-window | `timed_taps`, `check_ins`, `check_outs`, `weekend_taps`, `passes_minimum` |
| `row_audit` | `05_row_audit.sql` | source file | `raw_rows`, `no_station`, `date_only`, `timed_outside_windows`, `timed_in_windows`, `unmapped_station` |

Parquet cuts the data scanned per query: a three-month query reads 0.1 MB instead of 1,545 MB of CSV, and a two-column query over everything reads 8.1 MB. Curated data is 80 MB against 1,545 MB of raw CSV.

## Feature table

**One row = one station in one window.** Each row summarises every timed tap at that station in that window (median about 11,000 taps).

| Window | Rows | Timed taps |
|---|---|---|
| W17/18 | 47 | 425,595 |
| W18/19 | 45 | 641,446 |
| W19/20 | 46 | 630,175 |
| W21/22 | 53 | 843,378 |
| W24/25 | 53 | 800,365 |
| **Total** | **244** | 3,340,959 |

The one removed row (Energy in W18/19, 254 taps) is listed in `results/features/removed.csv`.

### Time bands

The day is split into five bands. The night (00-05) and early (05-07) bands are merged because night alone had too few taps.

| Band | Hours |
|---|---|
| `00_07` | 00:00 to 06:59 |
| `07_10` | morning peak |
| `10_16` | midday |
| `16_20` | evening peak |
| `20_24` | late evening |

### The 17 features

With `CI_b` and `CO_b` the check-ins and check-outs in band `b` for that station-window:

| Features | Count | Formula | Meaning |
|---|---|---|---|
| `check_in_share_<band>` | 5 | `CI_b / sum(CI)` | when people enter this station (the five add up to 1) |
| `check_out_share_<band>` | 5 | `CO_b / sum(CO)` | when people leave this station (the five add up to 1) |
| `net_flow_<band>` | 5 | `(CI_b - CO_b) / (CI_b + CO_b)`, from -1 to +1 | positive: more people leave from here; negative: more arrive |
| `weekend_share` | 1 | weekend taps / all taps | leisure and shopping signal |
| `volume_share` | 1 | station's taps / all taps in that window | how busy the station is |

Shares are used instead of raw counts because the data is a sample. Example, Business Bay in W24/25: morning net flow -0.58 (people arrive for work) and evening +0.50 (they leave).

### Scaling

Every feature is standardised across the 244 rows: `z = (x - mean) / std`, using the population standard deviation. The means and standard deviations are in `results/features/feature_summary.csv`.

### Files

| File | Contents |
|---|---|
| `features.parquet` | **model input**: keys plus 17 z-scored features |
| `features_unscaled.parquet` | the same rows before scaling, for reading and plotting |
| `removed.csv` | station-windows below 300 timed taps |
| `feature_summary.csv` | mean and standard deviation used for scaling |

Key columns in both Parquet files: `win`, `location_id`, `station`, `timed_taps`, `check_ins`, `check_outs`.

## Model input and output

**Input, all five methods:** `results/features/features.parquet`, a 244 x 17 matrix of z-scored features. Every method uses the same matrix so results compare directly. The key columns identify rows and are not used for clustering.

**Extra input, ST-GRSC only:** a station-window graph, planned as `edges.csv`:

- spatial links between neighbouring stations on the same line, within a window;
- temporal links between the same station in consecutive windows (the weighting across the 2- and 3-year gaps is still to be decided).

| Method | Uses the graph |
|---|---|
| K-means | no |
| Hierarchical (Ward) | no |
| DBSCAN | no |
| Spectral clustering (graph weight off) | no |
| ST-GRSC (proposed) | yes |

**Output, planned format, same for every method:** one row per station-window with `win`, `location_id`, `station`, `method`, the settings used (for example `k`, `alpha`) and the assigned `cluster`. DBSCAN marks outliers as noise. From these labels:

- five metrics: silhouette, Davies-Bouldin, Calinski-Harabasz, SSE, and ARI stability over 100 resamples of 80% of rows;
- the ablation: no graph, spatial links only, temporal links only, both;
- cluster profiles, a station-by-window type table, and the list of stations that changed type;
- a check against hand labels made before any results existed.

## Running it

### Python setup

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows Git Bash; on Mac or Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### Get the raw data

```bash
python scripts/download_parts.py --parts 1 2 300 586 900 1186 1500 1786 2100 2386
```

The stations, lines and official summary files are downloaded from Data Dubai by hand into `data/raw/`.

### Build the feature table locally

```bash
python src/build_features.py
```

It prints `10 parts, 3,340,959 taps, 245 station-windows, 244 kept, 1 removed, 17 features`.

### Run the AWS pipeline

Teammates: first follow `docs/TEAM_SETUP.md`, then:

```bash
export AWS_PROFILE=data-mining
bash pipeline/run_all.sh                    # rebuilds curated tables, ends with 10 PASS checks
bash pipeline/compare_with_local.sh         # confirms AWS matches results/features/
```

Only the project owner runs `infra/` and `pipeline/upload_raw.sh`.

## Working together

- One branch per person; merge into `main` through a pull request reviewed by one other member.
- Never commit `data/`, `infra/config.local.sh`, or any AWS keys or passwords.
- File names and columns in `results/features/` are the contract between stages. Change them only after telling the group.

## Known limitations

- The study runs from Nov 2017 to Feb 2025. 2023 has no tap times, and no window covers the COVID period.
- Friday behaviour changes across windows after the 2022 weekend change, which can look like a station changing type.
- The station renames are not yet confirmed against RTA.
- The data is a sample: about 5 timed taps per 1,000 riders in W24/25. Station shares still match the official monthly counts closely (correlation 0.998 across 47 stations).
