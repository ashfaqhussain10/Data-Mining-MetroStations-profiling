#!/usr/bin/env bash
# Deletes the bucket and ALL its contents, the Glue database, the Athena workgroup
# and the budget. Team users and the role are left for you to remove separately.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

echo "This permanently deletes s3://$BUCKET and everything in it,"
echo "plus Glue database $GLUE_DATABASE, workgroup $WORKGROUP and budget $BUDGET_NAME."
read -r -p "Type the bucket name to confirm: " answer
if [[ "$answer" != "$BUCKET" ]]; then
  echo "Name did not match. Nothing was deleted."
  exit 1
fi

aws s3 rb "s3://$BUCKET" --force
aws glue delete-database --name "$GLUE_DATABASE" --region "$REGION"
aws athena delete-work-group --work-group "$WORKGROUP" --region "$REGION" --recursive-delete-option
aws budgets delete-budget --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME"
echo "Done."
