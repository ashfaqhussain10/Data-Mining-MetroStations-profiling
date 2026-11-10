#!/usr/bin/env bash
# Helpers for running Athena queries. Source this file after infra/config.sh.

# Runs one statement, waits for it, and stops the pipeline if it fails.
run_query() {
  local sql="$1" id state reason
  id="$(aws athena start-query-execution --region "$REGION" --work-group "$WORKGROUP" \
    --query-execution-context "Database=$GLUE_DATABASE" --query-string "$sql" \
    --query QueryExecutionId --output text)"
  while true; do
    state="$(aws athena get-query-execution --region "$REGION" --query-execution-id "$id" \
      --query QueryExecution.Status.State --output text)"
    case "$state" in
      SUCCEEDED) break ;;
      FAILED|CANCELLED)
        reason="$(aws athena get-query-execution --region "$REGION" --query-execution-id "$id" \
          --query QueryExecution.Status.StateChangeReason --output text)"
        echo "Query $state: $reason" >&2
        return 1 ;;
    esac
    sleep 2
  done
  LAST_QUERY_ID="$id"
  aws athena get-query-execution --region "$REGION" --query-execution-id "$id" \
    --query 'QueryExecution.Statistics.[DataScannedInBytes,TotalExecutionTimeInMillis]' --output text |
    awk '{printf "  ok: %.1f MB scanned, %.1f s\n", $1 / 1000000, $2 / 1000}'
}

# Runs a .sql file, splitting statements on lines holding only a semicolon.
run_sql_file() {
  local file="$1" statement="" line
  echo "$(basename "$file")"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    if [[ "$line" == ";" ]]; then
      run_query "$statement"
      statement=""
    else
      statement+="${line//__BUCKET__/$BUCKET}"$'\n'
    fi
  done < "$file"
  if [[ -n "${statement//[[:space:]]/}" ]]; then
    run_query "$statement"
  fi
}
