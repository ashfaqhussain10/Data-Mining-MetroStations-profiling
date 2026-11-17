#!/usr/bin/env bash
# Downloads the feature tables that Athena built and saves them in results/features/,
# where every model reads them. Run after pipeline/run_all.sh.
set -euo pipefail
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PIPELINE_DIR/../infra/config.sh"
source "$PIPELINE_DIR/athena.sh"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

download() {
  run_query "$2" >/dev/null
  aws s3 cp "s3://$BUCKET/athena-results/$LAST_QUERY_ID.csv" "$work/$1.csv" --only-show-errors
}
download features "SELECT * FROM features"
download features_unscaled "SELECT * FROM features_unscaled"
download removed "SELECT win, location_id, station, timed_taps, check_ins, check_outs FROM station_window_totals WHERE NOT passes_minimum"

"${PYTHON:-python}" "$PIPELINE_DIR/export_features.py" "$work" "$@"
