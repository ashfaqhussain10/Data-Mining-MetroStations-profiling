#!/usr/bin/env bash
# Downloads Athena's summary tables and compares them with results/features/.
set -euo pipefail
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PIPELINE_DIR/../infra/config.sh"
source "$PIPELINE_DIR/athena.sh"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

for table in band_counts station_window_totals; do
  run_query "SELECT * FROM $table" >/dev/null
  aws s3 cp "s3://$BUCKET/athena-results/$LAST_QUERY_ID.csv" "$work/$table.csv" --only-show-errors
done

"${PYTHON:-python}" "$PIPELINE_DIR/compare_with_local.py" "$work"
