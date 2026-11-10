#!/usr/bin/env bash
# Sets up teammate access:
#   - Role "$TEAM_ROLE" with narrow access (this project's bucket, Athena workgroup and
#     Glue database only). Raw data and the station map cannot be changed or deleted.
#   - One IAM user per name in TEAM_USERS, with console sign-in and an access key.
#     Users can only change their own password and keys, and switch into the role.
# No MFA, by decision. Passwords and keys are written to CREDENTIALS_DIR, outside
# OneDrive, and never printed. Safe to rerun: existing roles, users, logins and keys stay.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

CREDENTIALS_DIR="${CREDENTIALS_DIR:-$HOME/metro-team-credentials}"
if [[ -z "$TEAM_USERS" ]]; then
  echo "Set TEAM_USERS in infra/config.local.sh first." >&2
  exit 1
fi

fill() {
  sed -e "s/__BUCKET__/$BUCKET/g" -e "s/__REGION__/$REGION/g" -e "s/__ACCOUNT__/$ACCOUNT_ID/g" \
      -e "s/__WORKGROUP__/$WORKGROUP/g" -e "s/__DATABASE__/$GLUE_DATABASE/g" \
      -e "s/__ROLE__/$TEAM_ROLE/g" "$1"
}

trust_policy="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"AWS\":\"arn:aws:iam::$ACCOUNT_ID:root\"},\"Action\":\"sts:AssumeRole\"}]}"
if aws iam get-role --role-name "$TEAM_ROLE" >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name "$TEAM_ROLE" --policy-document "$trust_policy"
  echo "Role exists: $TEAM_ROLE (trust policy refreshed)"
else
  aws iam create-role --role-name "$TEAM_ROLE" --assume-role-policy-document "$trust_policy" \
    --max-session-duration 14400 --tags "Key=project,Value=$PROJECT_TAG" >/dev/null
  echo "Role created: $TEAM_ROLE"
fi
aws iam put-role-policy --role-name "$TEAM_ROLE" --policy-name project-access \
  --policy-document "$(fill "$INFRA_DIR/team_policy.json")"
echo "Narrow access policy attached"

new_password() {
  python -c "import secrets,string
pool = string.ascii_letters + string.digits + '!@#%^*-_=+'
while True:
    p = ''.join(secrets.choice(pool) for _ in range(20))
    if any(c.islower() for c in p) and any(c.isupper() for c in p) and any(c.isdigit() for c in p) and any(not c.isalnum() for c in p):
        print(p); break"
}

mkdir -p "$CREDENTIALS_DIR"
user_policy="$(fill "$INFRA_DIR/user_self_service_policy.json")"
for user in $TEAM_USERS; do
  if aws iam get-user --user-name "$user" >/dev/null 2>&1; then
    echo "User exists: $user"
  else
    aws iam create-user --user-name "$user" --tags "Key=project,Value=$PROJECT_TAG" >/dev/null
    echo "User created: $user"
  fi
  aws iam put-user-policy --user-name "$user" --policy-name self-service-and-switch-role \
    --policy-document "$user_policy"

  password=""
  if aws iam get-login-profile --user-name "$user" >/dev/null 2>&1; then
    echo "  console login exists"
  else
    password="$(new_password)"
    aws iam create-login-profile --user-name "$user" --password "$password" --password-reset-required >/dev/null
    echo "  console login created (must change password at first sign-in)"
  fi

  key_id="" key_secret=""
  if [[ "$(aws iam list-access-keys --user-name "$user" --query 'length(AccessKeyMetadata)' --output text)" == "0" ]]; then
    read -r key_id key_secret < <(aws iam create-access-key --user-name "$user" \
      --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text)
    echo "  access key created"
  else
    echo "  access key exists"
  fi

  if [[ -n "$password" || -n "$key_id" ]]; then
    {
      echo "Dubai Metro project: AWS access for $user"
      echo "Send this privately. Delete this file once it has been delivered."
      echo
      echo "Console sign-in:  https://$ACCOUNT_ID.signin.aws.amazon.com/console"
      echo "User name:        $user"
      [[ -n "$password" ]] && echo "First password:   $password   (you must change it at first sign-in)"
      echo "Switch role:      https://signin.aws.amazon.com/switchrole?roleName=$TEAM_ROLE&account=$ACCOUNT_ID"
      echo
      echo "Command line"
      echo "Region:           $REGION"
      [[ -n "$key_id" ]] && echo "Access key ID:    $key_id"
      [[ -n "$key_secret" ]] && echo "Secret key:       $key_secret"
      echo "Role ARN:         arn:aws:iam::$ACCOUNT_ID:role/$TEAM_ROLE"
    } > "$CREDENTIALS_DIR/$user.txt"
    echo "  details saved to $CREDENTIALS_DIR/$user.txt"
  fi
done

echo "Done. Teammate steps are in docs/TEAM_SETUP.md."
