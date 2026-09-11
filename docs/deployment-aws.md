# AWS demo deployment

This document deploys the existing Cost Detector MVP as a controlled demo/staging environment. It does not add product features and does not claim production readiness.

## Architecture

Terraform in [`infra/terraform`](../infra/terraform) creates one dedicated VPC across two Availability Zones:

- Public subnets: one internet-facing Application Load Balancer and one NAT Gateway.
- Private subnets: ECS Fargate backend/frontend tasks, RDS PostgreSQL, and ElastiCache Redis.
- ALB `/api/*`, `/docs`, and `/openapi.json` route to FastAPI; all other paths route to Next.js.
- Secrets Manager provides `DATABASE_URL`, `REDIS_URL`, and `JWT_SECRET_KEY` to ECS.
- The backend ECS task role calls Cost Explorer and STS; no AWS access keys are placed in the image or task definition.
- ECR repositories are immutable and scan images on push.

The single NAT Gateway is intentional for this small environment: it gives private ECS tasks reliable outbound access for image pulls, package/provider APIs, and AWS services, but it has a fixed hourly and data-processing cost. VPC endpoints can reduce that cost later, at the expense of more infrastructure and endpoint charges.

## Prerequisites

Install and authenticate:

- AWS CLI with permission to create the demo resources and pass the ECS roles.
- Terraform >= 1.6.
- Docker with access to the target AWS account’s ECR.
- An AWS region with at least two Availability Zones.

The deployment operator needs infrastructure permissions. This is separate from the restricted ECS task role. Do not give the application task AdministratorAccess or PowerUserAccess.

## Bootstrap and image build

From the repository root:

```powershell
$env:AWS_REGION = "us-east-1"
$env:AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$env:IMAGE_TAG = (git rev-parse --short=12 HEAD)
$env:ECR_PREFIX = "$env:AWS_ACCOUNT_ID.dkr.ecr.$env:AWS_REGION.amazonaws.com/cost-detector-demo"
```

Initialize Terraform and create only the ECR repositories first:

```powershell
Copy-Item infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform apply `
  -target=aws_ecr_repository.backend `
  -target=aws_ecr_repository.frontend
```

Build and push immutable images. `NEXT_PUBLIC_API_BASE_URL` is compiled into Next.js, so use the final public origin when a domain exists. For first validation, use the ALB URL after the initial infrastructure apply, then rebuild the frontend and update the service.

```powershell
aws ecr get-login-password --region $env:AWS_REGION |
  docker login --username AWS --password-stdin "$env:AWS_ACCOUNT_ID.dkr.ecr.$env:AWS_REGION.amazonaws.com"

docker build --tag "$env:ECR_PREFIX/backend:$env:IMAGE_TAG" .
docker push "$env:ECR_PREFIX/backend:$env:IMAGE_TAG"

docker build --build-arg NEXT_PUBLIC_API_BASE_URL=$env:APP_ORIGIN `
  --tag "$env:ECR_PREFIX/frontend:$env:IMAGE_TAG" frontend
docker push "$env:ECR_PREFIX/frontend:$env:IMAGE_TAG"
```

Set the two image variables in `terraform.tfvars` to those exact immutable URIs.

## Provision and migrate

```powershell
terraform -chdir=infra/terraform plan
terraform -chdir=infra/terraform apply
terraform -chdir=infra/terraform output
```

Run migrations as a one-off ECS task before relying on the backend service. Do not run migrations automatically on every container start. The task definition already contains the production secret references; override only the command:

```powershell
$cluster = terraform -chdir=infra/terraform output -raw ecs_cluster_name
$taskdef = aws ecs describe-services --cluster $cluster --services (terraform -chdir=infra/terraform output -raw ecs_backend_service_name) --query 'services[0].taskDefinition' --output text
$subnets = (terraform -chdir=infra/terraform output -json private_subnet_ids | ConvertFrom-Json) -join ','
$sg = terraform -chdir=infra/terraform output -raw ecs_security_group_id

aws ecs run-task --cluster $cluster --launch-type FARGATE --task-definition $taskdef `
  --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$sg],assignPublicIp=DISABLED}" `
  --overrides '{"containerOverrides":[{"name":"backend","command":["alembic","upgrade","head"]}]}'
```

Wait for the migration task to stop successfully, then confirm both ECS services have one healthy task.

## HTTPS and domain

The initial Terraform stack exposes HTTP on the ALB DNS name so deployment does not depend on a domain. For HTTPS, request an ACM certificate in the same region, validate it through Route 53, add an HTTPS listener, and change the HTTP listener to redirect to HTTPS. Set `app_origin` to the final `https://` origin and rebuild the frontend so CORS and its API base URL are correct.

## Validation

```powershell
$url = terraform -chdir=infra/terraform output -raw alb_url
Invoke-WebRequest "$url/api/v1/health" -UseBasicParsing
Invoke-WebRequest "$url/login" -UseBasicParsing
aws sts get-caller-identity
```

The health response must report both PostgreSQL and Redis as `up`. Verify registration/login, dashboard, Cost Explorer, Copilot, anomalies, optimization, budgets, and alerts through the ALB URL. The ALB health check intentionally uses `/api/v1/health`, not a Cost Explorer call.

The backend task role should be verified from an ECS task with STS `GetCallerIdentity`. Cost Explorer data is account-scoped; do not claim live billing validation until the intended account returns the expected data.

## Rollback and cleanup

To roll back an application version, update `backend_image` or `frontend_image` to a previous immutable tag and run `terraform apply`; ECS performs the rolling replacement. Keep the previous ECR image until the rollback is complete.

For demo cleanup:

```powershell
terraform -chdir=infra/terraform destroy
```

This removes the demo VPC, NAT Gateway, ALB, ECS, RDS, Redis, ECR, log groups, and Secrets Manager secret. RDS final snapshots are intentionally skipped for this disposable environment; export anything needed before destroying it.

## Cost safety & Architecture Options

The demo stack uses:
- 1 Fargate backend task (0.5 vCPU / 1 GB RAM)
- 1 Fargate frontend task (0.25 vCPU / 0.5 GB RAM)
- 1 single-AZ RDS PostgreSQL instance (`db.t4g.micro`, 20 GB gp3)
- 1 single-node ElastiCache Redis cache (`cache.t4g.micro`)
- 1 NAT Gateway (single AZ)
- 1 Application Load Balancer (ALB)
- ECR repositories with lifecycle policies (retaining last 10 images)
- CloudWatch log groups (14-day retention)

### Monthly Cost Breakdown (us-east-1 estimate)

| Resource | Size / Tier | Estimated Cost/Month |
|---|---|---|
| **NAT Gateway** | 1 NAT GW + 1 Elastic IP (~$0.045/hr + data) | ~$32.85 |
| **Application Load Balancer** | 1 ALB (~$0.0225/hr + LCU) | ~$16.43 |
| **RDS PostgreSQL** | `db.t4g.micro` (single-AZ, 20 GB gp3) | ~$14.50 |
| **ElastiCache Redis** | `cache.t4g.micro` (single-node) | ~$12.41 |
| **ECS Fargate (Backend)** | 0.5 vCPU / 1 GB (always on) | ~$14.60 |
| **ECS Fargate (Frontend)** | 0.25 vCPU / 0.5 GB (always on) | ~$7.30 |
| **ECR & CloudWatch Logs** | < 5 GB storage | ~$0.50 |
| **Total Estimated Run Rate** | | **~$98.50 / month** (~$3.28 / day) |

> [!TIP]
> **Zero-NAT Gateway Architecture Alternative (Ultra-low-cost MVP)**:
> If this environment is strictly disposable and saving ~$33/month is desired:
> 1. In `network.tf`, eliminate `aws_nat_gateway` and `aws_eip.nat`.
> 2. In `ecs.tf`, place ECS tasks in `aws_subnet.public` with `assign_public_ip = true`.
> 3. Security groups still restrict ingress to ALB only, preserving application boundary isolation.
> 4. Keep RDS and Redis in private subnets with no public access.
> This lowers the monthly cost to **~$65/month**.

Configure an **AWS Budget Alert** (e.g. at $10 threshold) before running infrastructure long-term to ensure immediate notification of unexpected charges.

---

## Controlled Real AWS Billing Validation Procedure

> [!IMPORTANT]
> **No Mock Data Principle**:
> The application must never fabricate billing data or falsify provider responses.
> When AWS returns $0.00 for a fresh or empty account, Cost Detector displays a valid zero-cost state.
> The purpose of this test is to generate a verifiable, controlled AWS charge and trace it end-to-end:
> `AWS Resource Usage → AWS Billing Pipeline → Cost Explorer API → Cost Detector Backend → Next.js Dashboard`

### Phase 1: Verify Initial Zero / Baseline State

1. Query Cost Explorer health:
   ```bash
   curl -s http://<ALB_URL>/api/v1/aws/health | jq .
   # Expected output: {"provider":"aws","healthy":true,"mode":"real"}
   ```
   Confirm `"mode": "real"`. If `"mode": "mock"`, check `AWS_USE_MOCK_DATA` environment variable.

2. Query current month-to-date cost:
   ```bash
   # Log in to retrieve JWT access token
   TOKEN=$(curl -s -X POST http://<ALB_URL>/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"demo@example.com","password":"demo-password"}' | jq -r .access_token)

   # Query AWS costs for yesterday to today (UTC)
   START_DATE=$(date -u -d "yesterday" +%Y-%m-%d 2>/dev/null || date -u -v-1d +%Y-%m-%d)
   END_DATE=$(date -u +%Y-%m-%d)
   curl -s -H "Authorization: Bearer $TOKEN" \
     "http://<ALB_URL>/api/v1/aws/costs?start_date=$START_DATE&end_date=$END_DATE" | jq .
   ```
3. Confirm that a valid response with $0.00 total cost returns HTTP 200 with:
   ```json
   {
     "provider": "aws",
     "currency": "USD",
     "total_cost": 0.0,
     "services": [],
     "daily_costs": []
   }
   ```
   **Important**: An empty or $0 cost is a valid state; an API failure (HTTP 403, 500, or 502) is NOT a valid zero.

---

### Phase 2: Create a Minimal Controlled Test Resource

To generate a real, billable event without runaway charges, create a minimal non-free-tier resource or small usage pattern. A minimal S3 Standard object or standalone CloudWatch metric write is safe, controlled, and easy to clean up.

#### Recommended: Temporary S3 Standard Storage Test
1. Generate a unique bucket name:
   ```bash
   BUCKET_NAME="costdetector-test-$(aws sts get-caller-identity --query Account --output text)-$(date +%s)"
   ```
2. Create the bucket with test tracking tags:
   ```bash
   aws s3api create-bucket \
     --bucket "$BUCKET_NAME" \
     --region us-east-1
   aws s3api put-bucket-tagging \
     --bucket "$BUCKET_NAME" \
     --tagging 'TagSet=[{Key=CostDetectorTest,Value=true},{Key=Environment,Value=Validation}]'
   ```
3. Upload a small payload (e.g. 10 MB):
   ```bash
   dd if=/dev/urandom of=test_payload.bin bs=1M count=10
   aws s3 cp test_payload.bin "s3://$BUCKET_NAME/payload.bin"
   ```
4. **Expected Cost**: < $0.001 (less than one-tenth of one cent).
5. **Runtime**: Leave the object in the bucket for **1 to 2 hours** to allow AWS metering records to register S3 storage byte-hours.

---

### Phase 3: Resource Cleanup & Deletion Verification

Immediately after the 1–2 hour test window, delete the test resource:
```bash
# Delete the payload object
aws s3 rm "s3://$BUCKET_NAME/payload.bin"

# Delete the test bucket
aws s3api delete-bucket --bucket "$BUCKET_NAME"

# Verify deletion (must return NoSuchBucket or 404)
aws s3 ls "s3://$BUCKET_NAME" || echo "Deletion verified: bucket no longer exists"

# Clean up local file
rm -f test_payload.bin
```

---

### Phase 4: Account for AWS Billing Data Latency

> [!WARNING]
> **Billing Latency Expectation**:
> AWS Cost Explorer updates its dataset **once every 24 hours** (typically between 00:00 and 12:00 UTC for the previous calendar day).
> Newly generated usage will NOT appear in Cost Explorer immediately.
> Attempting to query Cost Explorer 10 minutes after creating a resource will show $0.00.
> **Validation Schedule**: Wait 24–48 hours after generating usage before performing Phase 5.

---

### Phase 5: End-to-End Validation & Verification

Once 24 hours have elapsed:

1. **Query AWS Cost Explorer directly via AWS CLI**:
   ```bash
   aws ce get-cost-and-usage \
     --time-period Start=$START_DATE,End=$END_DATE \
     --granularity DAILY \
     --metrics "UnblendedCost" \
     --group-by Type=DIMENSION,Key=SERVICE
   ```
2. **Query Cost Detector Backend API**:
   ```bash
   curl -s -H "Authorization: Bearer $TOKEN" \
     "http://<ALB_URL>/api/v1/aws/costs?start_date=$START_DATE&end_date=$END_DATE" | jq .
   ```
3. **Verify Field-by-Field Parity**:
   - `provider`: Must be `"aws"`.
   - `services`: Must list `"Amazon Simple Storage Service"` (or whichever AWS service was used).
   - `total_cost`: Must match the sum of unblended costs reported by AWS CE.
   - `daily_costs`: Must reflect the date bucket when the test resource ran.
4. **Verify in Frontend UI**:
   - Navigate to `http://<ALB_URL>` in the browser.
   - Select the date range corresponding to `$START_DATE` through `$END_DATE`.
   - Verify the AWS service breakdown card displays the exact service name and amount.
   - Verify the daily trend chart reflects the test spike.

---

## Troubleshooting

- **ECS tasks fail to start**:
  - Inspect ECS service events: `aws ecs describe-services --cluster cost-detector-demo --services cost-detector-demo-backend`
  - Inspect CloudWatch logs: `/ecs/cost-detector-demo/backend`
- **Health returns 503 (`unhealthy`)**:
  - Check database: Did `alembic upgrade head` run? Check RDS security group allows port 5432 from ECS security group.
  - Check Redis: Ensure transit encryption (TLS) matches the `rediss://` URL protocol.
- **Backend has no AWS data / returns 403**:
  - Confirm ECS task role is attached (`cost-detector-demo-ecs-task`).
  - Verify policy has `ce:GetCostAndUsage`, `ce:GetCostForecast`, `ce:GetDimensionValues`, `ce:GetTags`, `sts:GetCallerIdentity`.
  - Check that Cost Explorer is enabled in the target AWS account (AWS Billing Console > Cost Management > Cost Explorer).
- **Frontend calls localhost**:
  - Rebuild frontend with `NEXT_PUBLIC_API_BASE_URL` set to the public ALB URL (`http://<alb-dns>`). Next.js inlines `NEXT_PUBLIC_` variables at build time.
- **ALB target group shows unhealthy**:
  - Backend target group: path `/api/v1/health`, port 8000, expects 200.
  - Frontend target group: path `/login`, port 3000, expects 200-399.
  - Ensure ECS security group permits ingress on 8000 and 3000 from ALB security group.

