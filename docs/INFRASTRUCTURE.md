# Infrastructure & Deployment Guide

## Architecture Overview

BBP HKBG runs on AWS as a serverless application:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  CloudFront  │────▶│  S3 (static) │     │  Cognito User   │
│  Distribution│     │  Vue.js SPA  │     │  Pool + Google   │
└──────┬──────┘     └──────────────┘     │  Federation      │
       │                                  └────────┬────────┘
       │                                           │
┌──────▼──────┐     ┌──────────────┐              │
│ API Gateway  │────▶│  14 Lambda   │◀─────────────┘
│ REST API     │     │  Functions   │       (Cognito Authorizer)
└─────────────┘     └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ DynamoDB  │ │    S3    │ │ Textract │
        │ (5 tables)│ │  (docs)  │ │ Bedrock  │
        └──────────┘ └──────────┘ └──────────┘
```

## CDK Stacks

The infrastructure is defined in `infra/lib/` as five CDK stacks:

| Stack | File | Purpose |
|-------|------|---------|
| `BbpHkbgStorageStack` | `storage-stack.ts` | S3 buckets (documents + static site) and 5 DynamoDB tables |
| `BbpHkbgAuthStack` | `auth-stack.ts` | Cognito User Pool, Google IdP, OAuth app client |
| `BbpHkbgApiStack` | `api-stack.ts` | API Gateway REST API, 14 Lambda functions, Cognito authorizer |
| `BbpHkbgFrontendStack` | `frontend-stack.ts` | CloudFront distribution with OAC for S3 |
| `BbpHkbgCiCdStack` | `cicd-stack.ts` | GitHub Actions OIDC provider + IAM deploy role |

Stacks are composed in `infra/bin/infra.ts` and deploy in dependency order.

## DynamoDB Tables

| Table | Partition Key | Sort Key | GSIs |
|-------|--------------|----------|------|
| `bbp-hkbg-applications` | `giveaway_year` (S) | `application_id` (S) | `status-index`, `agency-index` |
| `bbp-hkbg-audit-log` | `year_month` (S) | `timestamp#user_id` (S) | `user-index`, `action-index` |
| `bbp-hkbg-users` | `user_id` (S) | — | `email-index` |
| `bbp-hkbg-saved-reports` | `user_id` (S) | `report_id` (S) | — |
| `bbp-hkbg-config` | `config_key` (S) | — | — |

All tables use PAY_PER_REQUEST billing and AWS-managed encryption.

## S3 Buckets

| Bucket | Purpose | Lifecycle |
|--------|---------|-----------|
| `bbp-hkbg-documents` | Uploads, drawings, versions, exports | Glacier after 365d; exports expire after 7d |
| `bbp-hkbg-static` | Vue.js SPA (served via CloudFront) | Auto-delete on stack removal |

</text>
</invoke>

## Lambda Functions

All functions use Python 3.12 runtime. Source code lives in `lambda/<function_name>/handler.py` with shared utilities in `lambda/shared/`.

| Function | Route(s) | Auth | Purpose |
|----------|----------|------|---------|
| `submit_application` | `POST /api/applications` | Public | Digital form submission |
| `generate_presigned_url` | `POST /api/uploads/presign` | Public | S3 upload URLs |
| `process_document` | S3 trigger (`uploads/`) | N/A | Textract + Bedrock OCR pipeline |
| `get_applications` | `GET /api/applications` | Cognito | List/search/filter applications |
| `get_application_detail` | `GET /api/applications/{id}` | Cognito | Full application record |
| `update_application` | `PUT /api/applications/{id}`, status, bike-number, drawing-keywords | Cognito | Edit application fields |
| `export_data` | `POST /api/exports/*` | Cognito | Bike build list, family contact list |
| `manage_reports` | `GET/POST/DELETE /api/reports/saved/*` | Cognito | Saved report CRUD |
| `run_report` | `POST /api/reports/run`, `POST /api/reports/export` | Cognito | Run + export reports |
| `get_cost_data` | `GET /api/cost-dashboard`, `PUT /api/cost-dashboard/budget` | Cognito | AWS Cost Explorer data |
| `manage_users` | `GET/POST/PUT/DELETE /api/users/*` | Cognito | User account management |
| `get_audit_log` | `GET /api/audit-log`, `POST /api/audit-log/export` | Cognito | Audit trail |
| `manage_giveaway_year` | `GET/POST /api/giveaway-years/*` | Cognito | Year lifecycle management |
| `get_auth_me` | `GET /api/auth/me` | Cognito | Current user info |

---

## Prerequisites

- AWS CLI v2 configured with appropriate credentials
- Node.js 20+
- Python 3.12
- AWS CDK CLI (`npm install -g aws-cdk`)
- A bootstrapped CDK environment (`cdk bootstrap aws://<ACCOUNT_ID>/<REGION>`)

---

## First-Time Setup

### 1. Bootstrap CDK

```bash
cd infra
npm install
npx cdk bootstrap aws://<ACCOUNT_ID>/us-west-2
```

### 2. Set up Google OAuth credentials

Create a Google OAuth 2.0 client in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials):
- Application type: Web application
- Authorized redirect URI: `https://<your-cognito-domain>.auth.us-east-1.amazoncognito.com/oauth2/idpresponse`

You'll need the Client ID and Client Secret for the auth stack deployment.

### 3. Deploy the CI/CD stack (one-time)

This creates the GitHub OIDC provider and IAM role:

```bash
npx cdk deploy BbpHkbgCiCdStack \
  --parameters GitHubOrg=<your-github-org> \
  --parameters GitHubRepo=<your-repo-name>
```

Note the `GitHubActionsRoleArn` output — you'll need it for GitHub secrets.

### 4. Deploy all stacks

```bash
npx cdk deploy --all \
  --parameters BbpHkbgAuthStack:GoogleClientId=<GOOGLE_CLIENT_ID> \
  --parameters BbpHkbgAuthStack:GoogleClientSecret=<GOOGLE_CLIENT_SECRET> \
  --parameters BbpHkbgAuthStack:CallbackUrl=https://<your-cloudfront-domain>/callback \
  --parameters BbpHkbgAuthStack:LogoutUrl=https://<your-cloudfront-domain>
```

> On first deploy, you won't know the CloudFront domain yet. Deploy once with the defaults (`http://localhost:5173/callback`), grab the CloudFront URL from the `BbpHkbgFrontendStack` outputs, then update the auth stack.

---

## GitHub Actions CI/CD

### Pipelines

Two workflows in `.github/workflows/`:

| Workflow | Trigger | What it does |
|----------|---------|-------------|
| `backend-deploy.yml` | Push to `main` changing `lambda/**` or `infra/**` | Lint, test, `cdk deploy --all` |
| `frontend-deploy.yml` | Push to `main` changing `frontend/**` | Lint, test, build, S3 sync, CloudFront invalidation |

Both use GitHub OIDC federation to assume the deploy role — no long-lived AWS keys needed.

### Required GitHub Secrets

Configure these in your repo under Settings → Secrets and variables → Actions:

| Secret | Value | Where to get it |
|--------|-------|-----------------|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/bbp-hkbg-github-actions-deploy` | Output of `BbpHkbgCiCdStack` deployment |

### Required GitHub Variables (optional but recommended)

You can also set these as repository variables for visibility:

| Variable | Value | Purpose |
|----------|-------|---------|
| `AWS_REGION` | `us-west-2` | Deployment region (hardcoded in workflows, change if needed) |

### CloudFormation Parameters via CDK

The `cdk deploy` in the backend pipeline runs with `--require-approval never`. On first deploy or when auth parameters change, you need to pass them. For CI/CD, store them as CloudFormation parameter overrides or use AWS Systems Manager Parameter Store:

```bash
# Store parameters in SSM (one-time, from your local machine)
aws ssm put-parameter --name "/bbp-hkbg/google-client-id" --value "<ID>" --type SecureString
aws ssm put-parameter --name "/bbp-hkbg/google-client-secret" --value "<SECRET>" --type SecureString
```

Then reference them in the CDK stack or pass them via the workflow.

---

## Environment Variables

### Lambda Functions

Set automatically by CDK. Key variables per function:

| Variable | Description | Set by |
|----------|-------------|--------|
| `APPLICATIONS_TABLE_NAME` | DynamoDB applications table | CDK |
| `AUDIT_LOG_TABLE_NAME` | DynamoDB audit log table | CDK |
| `USERS_TABLE_NAME` | DynamoDB users table | CDK |
| `SAVED_REPORTS_TABLE_NAME` | DynamoDB saved reports table | CDK |
| `CONFIG_TABLE_NAME` | DynamoDB config table | CDK |
| `DOCUMENTS_BUCKET_NAME` | S3 documents bucket | CDK |
| `USER_POOL_ID` | Cognito User Pool ID | CDK |
| `AUTH_ENABLED` | Enable/disable auth (`true`/`false`) | CDK |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | CDK (via `allowedOrigins` prop on `ApiStack`) |

### Frontend (Vite)

Set via `.env` files or CI/CD environment. See `frontend/.env.example`.

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | API Gateway base URL | `/api` (uses Vite proxy locally) |
| `VITE_AUTH_ENABLED` | Enable/disable auth in the UI | `true` |

For production builds in CI, set `VITE_API_BASE_URL` to your API Gateway URL:

```
https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/api
```

---

## CORS Configuration

CORS origins are configurable via the `allowedOrigins` prop on `ApiStack`:

```typescript
// infra/bin/infra.ts
const apiStack = new ApiStack(app, 'BbpHkbgApiStack', {
  storageStack,
  authStack,
  allowedOrigins: [
    'https://d1234abcdef.cloudfront.net',  // production
    'http://localhost:5173',                // local dev
  ],
});
```

This sets:
- API Gateway preflight `Access-Control-Allow-Origin` responses
- `ALLOWED_ORIGINS` env var on all Lambda functions (used in response headers)

For local development, the Vite dev server proxies `/api` requests, so CORS isn't a factor.

---

## Useful Commands

```bash
# From infra/
npx cdk synth              # Generate CloudFormation templates
npx cdk diff               # Preview changes
npx cdk deploy --all       # Deploy all stacks
npx cdk destroy --all      # Tear down (documents bucket is RETAIN)

# Run Lambda tests (each directory separately due to module naming)
for d in lambda/*/; do
  if ls "$d"test_*.py 1>/dev/null 2>&1; then
    python -m pytest "$d" -q
  fi
done

# Run frontend tests
cd frontend && npx vitest run

# Run infra tests
cd infra && npm test
```

---

## Stack Outputs Reference

After deployment, these outputs are available:

| Output | Export Name | Description |
|--------|-----------|-------------|
| API URL | `BbpHkbgApiUrl` | API Gateway endpoint |
| API ID | `BbpHkbgApiId` | API Gateway REST API ID |
| CloudFront URL | `BbpHkbgDistributionUrl` | Frontend URL |
| CloudFront ID | `BbpHkbgDistributionId` | For cache invalidation |
| User Pool ID | `BbpHkbgUserPoolId` | Cognito User Pool |
| User Pool Client ID | `BbpHkbgUserPoolClientId` | SPA OAuth client |
| User Pool Domain | `BbpHkbgUserPoolDomainName` | Hosted UI domain prefix |
| Deploy Role ARN | `BbpHkbgGitHubActionsRoleArn` | GitHub Actions IAM role |

Retrieve any output with:
```bash
aws cloudformation describe-stacks --stack-name <StackName> \
  --query "Stacks[0].Outputs[?ExportName=='<ExportName>'].OutputValue" \
  --output text
```
