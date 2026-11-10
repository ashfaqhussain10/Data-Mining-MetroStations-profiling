#!/usr/bin/env bash
# Checks Athena's results against the numbers from notebooks/02_ten_parts_profile.ipynb.
set -euo pipefail
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PIPELINE_DIR/../infra/config.sh"
source "$PIPELINE_DIR/athena.sh"

failures=0
check() {
  local label="$1" expected="$2" sql="$3" actual
  run_query "$sql" >/dev/null
  actual="$(aws athena get-query-results --region "$REGION" --query-execution-id "$LAST_QUERY_ID" \
    --query 'ResultSet.Rows[1].Data[0].VarCharValue' --output text)"
  if [[ "$actual" == "$expected" ]]; then
    printf 'PASS  %-34s %s\n' "$label" "$actual"
  else
    printf 'FAIL  %-34s expected %s, got %s\n' "$label" "$expected" "$actual"
    failures=$((failures + 1))
  fi
}

check "Raw rows" 10484655 "SELECT sum(raw_rows) FROM row_audit"
check "No station" 9371 "SELECT sum(no_station) FROM row_audit"
check "Date-only with station" 5844691 "SELECT sum(date_only) FROM row_audit"
check "Timed outside windows" 1289634 "SELECT sum(timed_outside_windows) FROM row_audit"
check "Timed in windows" 3340959 "SELECT sum(timed_in_windows) FROM row_audit"
check "Unmapped stations" 0 "SELECT sum(unmapped_station) FROM row_audit"
check "Station-windows" 245 "SELECT count(*) FROM station_window_totals"
check "Rows at 300+ taps" 244 "SELECT count_if(passes_minimum) FROM station_window_totals"
check "Distinct stations" 53 "SELECT count(DISTINCT location_id) FROM station_window_totals"
check "Business Bay W24/25 taps" 28549 "SELECT timed_taps FROM station_window_totals WHERE station = 'Business Bay' AND win = 'W24/25'"

if [[ "$failures" -gt 0 ]]; then
  echo "$failures check(s) failed." >&2
  exit 1
fi
echo "All checks passed."
