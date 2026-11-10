# AWS setup for teammates

You get your sign-in details privately from Ashfaque. Never put them in the repo, a group chat or an email thread.

## What you can do

- Read everything in the project bucket.
- Run Athena queries in the `metro-profiling` workgroup.
- Rebuild the pipeline outputs (`curated/`), which `pipeline/run_all.sh` does.

You cannot change raw data, use other AWS services, or see billing. If something you need is blocked, ask Ashfaque.

## 1. Console (browser)

1. Open the console sign-in link from your details file and sign in with your user name and first password.
2. Set a new password when asked.
3. Open the **Switch role** link from your details file and press **Switch role**. You now work as `data-mining`.
4. Set the region to **Asia Pacific (Mumbai) ap-south-1**, open **Athena** and choose the `metro-profiling` workgroup.

## 2. Command line

You need the AWS CLI v2 and Git Bash (Windows) or a normal terminal (Mac, Linux).

```bash
# Your own key (from your details file)
aws configure --profile data-mining-user
#   Access key ID, secret key, region ap-south-1, output json

# The project role, which uses your key to switch
aws configure set role_arn <Role ARN from your details file> --profile data-mining
aws configure set source_profile data-mining-user --profile data-mining
aws configure set region ap-south-1 --profile data-mining

# Use the project role for everything in this terminal
export AWS_PROFILE=data-mining
aws sts get-caller-identity   # should show assumed-role/data-mining
```

## 3. Run the pipeline

From the repo folder:

```bash
cp infra/config.local.example.sh infra/config.local.sh   # leave the values as they are
export AWS_PROFILE=data-mining
bash pipeline/run_all.sh
```

It rebuilds the curated tables from the raw files and ends with 10 checks. All should say PASS. It takes about two minutes and costs about a cent.

Do not run anything in `infra/` or `pipeline/upload_raw.sh`. Those are for Ashfaque and will fail with your access.
