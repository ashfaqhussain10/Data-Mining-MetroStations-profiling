#!/usr/bin/env bash
# Copies the raw CSVs and the station map to S3. Each table gets its own prefix,
# because Athena reads every file under a table's location.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../infra/config.sh"

ROOT="$(cd "$INFRA_DIR/.." && pwd)"
RAW="$ROOT/data/raw"

aws s3 sync "$RAW" "s3://$BUCKET/raw/ridership/" --exclude "*" --include "metro_ridership_*.csv" --only-show-errors
aws s3 cp "$RAW"/metro_stations_*.csv "s3://$BUCKET/raw/stations/metro_stations.csv" --only-show-errors
aws s3 cp "$RAW"/metro_lines_*.csv "s3://$BUCKET/raw/lines/metro_lines.csv" --only-show-errors
aws s3 cp "$ROOT/results/profile/station_map_draft.csv" "s3://$BUCKET/reference/station_map/station_map.csv" --only-show-errors

echo "Uploaded:"
aws s3 ls "s3://$BUCKET/" --recursive --summarize | tail -2
