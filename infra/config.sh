#!/usr/bin/env bash
# Shared settings for the AWS scripts. Personal values live in config.local.sh,
# which git ignores. Copy config.local.example.sh to create it.

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$INFRA_DIR/config.local.sh" ]]; then
  echo "Missing infra/config.local.sh. Copy config.local.example.sh and fill it in." >&2
  exit 1
fi
source "$INFRA_DIR/config.local.sh"

export AWS_PAGER=""
REGION="ap-south-1"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

BUCKET="dubai-metro-profiling-${ACCOUNT_ID}"
GLUE_DATABASE="dubai_metro"
WORKGROUP="metro-profiling"
SCAN_LIMIT_BYTES=$((3 * 1024 * 1024 * 1024))  # raw CSVs are 1.5 GB, so a full pass must fit
BUDGET_NAME="metro-profiling-monthly"
TEAM_ROLE="data-mining"
PROJECT_TAG="dubai-metro-profiling"
