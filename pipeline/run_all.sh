#!/usr/bin/env bash
# Rebuilds every curated table from the raw files in S3, then checks the results.
# Raw data is never touched. Safe to rerun: curated output is replaced each time.
set -euo pipefail
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PIPELINE_DIR/../infra/config.sh"
source "$PIPELINE_DIR/athena.sh"
SQL_DIR="$PIPELINE_DIR/../sql"

echo "Clearing curated tables"
for table in curated_ridership band_counts station_window_totals row_audit; do
  run_query "DROP TABLE IF EXISTS $table"
done
aws s3 rm "s3://$BUCKET/curated/" --recursive --only-show-errors

for file in "$SQL_DIR"/0*.sql; do
  run_sql_file "$file"
done

bash "$PIPELINE_DIR/verify.sh"
