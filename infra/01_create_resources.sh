#!/usr/bin/env bash
# Creates the S3 bucket, Glue database, Athena workgroup and budget.
# Safe to rerun: anything that already exists is left in place.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

echo "Account ${ACCOUNT_ID}, region ${REGION}"

# S3 bucket, private and encrypted
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "Bucket exists: $BUCKET"
else
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
    --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
  echo "Bucket created: $BUCKET"
fi
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-tagging --bucket "$BUCKET" \
  --tagging "TagSet=[{Key=project,Value=$PROJECT_TAG}]"

# Glue database, used as the Athena catalog
if aws glue get-database --name "$GLUE_DATABASE" --region "$REGION" >/dev/null 2>&1; then
  echo "Glue database exists: $GLUE_DATABASE"
else
  aws glue create-database --region "$REGION" --database-input "{\"Name\":\"$GLUE_DATABASE\"}"
  echo "Glue database created: $GLUE_DATABASE"
fi

# Athena workgroup with a per-query scan limit. Enforcement stays off because tables
# write to their own curated/ folders, which Athena rejects in an enforced workgroup.
workgroup_config="{\"ResultConfiguration\":{\"OutputLocation\":\"s3://$BUCKET/athena-results/\"},\"EnforceWorkGroupConfiguration\":false,\"PublishCloudWatchMetricsEnabled\":true,\"BytesScannedCutoffPerQuery\":$SCAN_LIMIT_BYTES}"
if aws athena get-work-group --work-group "$WORKGROUP" --region "$REGION" >/dev/null 2>&1; then
  echo "Workgroup exists: $WORKGROUP"
else
  aws athena create-work-group --name "$WORKGROUP" --region "$REGION" \
    --configuration "$workgroup_config" --tags "Key=project,Value=$PROJECT_TAG"
  echo "Workgroup created: $WORKGROUP"
fi

# Monthly budget for this project's services only. IncludeCredit is false so spending
# still shows while AWS credits cover it.
budget="{\"BudgetName\":\"$BUDGET_NAME\",\"BudgetLimit\":{\"Amount\":\"$MONTHLY_BUDGET_USD\",\"Unit\":\"USD\"},\"TimeUnit\":\"MONTHLY\",\"BudgetType\":\"COST\",\"CostFilters\":{\"Service\":[\"Amazon Simple Storage Service\",\"Amazon Athena\",\"AWS Glue\"]},\"CostTypes\":{\"IncludeCredit\":false,\"IncludeRefund\":false}}"
notifications="[{\"Notification\":{\"NotificationType\":\"ACTUAL\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":80,\"ThresholdType\":\"PERCENTAGE\"},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$ALERT_EMAIL\"}]}]"
if aws budgets describe-budget --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME" >/dev/null 2>&1; then
  echo "Budget exists: $BUDGET_NAME"
else
  aws budgets create-budget --account-id "$ACCOUNT_ID" --budget "$budget" \
    --notifications-with-subscribers "$notifications"
  echo "Budget created: $BUDGET_NAME, alert at 80% of \$$MONTHLY_BUDGET_USD"
fi

echo "Done."
