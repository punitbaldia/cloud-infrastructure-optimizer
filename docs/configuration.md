# Configuration and deployment

All server settings are read from backend/.env or environment variables.
Secrets never belong in frontend VITE_* variables.

| Setting | Purpose |
|---|---|
| AUTH_ENABLED | true by default; false only for isolated tests |
| ADMIN_USERNAME / ADMIN_PASSWORD | Bootstrap first admin; password at least 12 characters |
| DATABASE_URL | SQLite local default, or postgresql+psycopg URL |
| JOB_MODE | local or celery |
| REDIS_URL | Redis broker for Celery |
| CLOUD_MODE | mock (default) or aws |
| ADAPTER_MODULE | app.cloud.mock for demo |
| AWS_ACCOUNT_ID / AWS_REGION | Single connected account and region |
| AWS_PROFILE | Optional local AWS CLI profile; leave empty for workload credentials |
| AWS_ROLE_ARN / AWS_EXTERNAL_ID | Optional monitoring AssumeRole configuration |
| AWS_EXECUTION_ROLE_ARN | Separate restricted execution role |
| LIVE_EXECUTION_ENABLED | false by default |
| EXPLANATION_MODE | mock or claude |
| ANTHROPIC_API_KEY / CLAUDE_MODEL | Credentials/model for Claude |
| SLACK_WEBHOOK_URL | Server-side Slack incoming webhook |
| SES_SENDER / ALERT_RECIPIENT | Verified SES sender and destination |
| CORS_ORIGINS | Comma-separated browser origins |

Changing ADMIN_PASSWORD after initial bootstrap does not change an existing user's
stored password. Treat it as an initial setup variable.
To change an existing password, use Settings → Account security with your current
password and a different new password of at least 12 characters. This revokes all
active sessions; sign in again with the new password. The bootstrap .env value
is not updated and cannot reset the existing account.
The startup setup script never overwrites existing .env files.

## AWS connection

Configure the standard Boto3 credential chain on the host (profile or workload role).
Do not paste credentials into the dashboard. Configure account/region/role and restart.
Use a separate empty database when switching mock/live mode to avoid mixing provenance.
Validate the connection in Settings, then run a scan. Validation checks STS identity;
specific read permissions are checked by collection calls.

Metric collection reads hourly aggregates over fourteen days. EC2 network totals
are converted to Bytes/hour; missing metrics are never zero-filled. CPU memory data
availability is explicit. Cost Explorer uses one cached daily collection, with
pagination for multi-service bills. The application supports one account and region.

Supported EC2 instances use AWS Price List Query API On-Demand rates. Estimates exclude
discounts, commitments, Free Tier and non-compute charges. Unsupported/ambiguous or
unavailable prices remain unavailable. The monitoring identity needs pricing:GetProducts.
RDS findings are review candidates, not target instance-class recommendations.

## Execution

The default simulator calls no AWS API. AWS stop requires:
- LIVE_EXECUTION_ENABLED=true configured on the server.
- Explicit dashboard approval and confirmation.
- Fresh evidence and a current eligibility recheck.
- A running EBS-backed EC2 instance.
- optimizer:managed=true and Environment=demo tags.
- A separate execution IAM role granting narrowly scoped StopInstances.

AWS_EXECUTION_ROLE_ARN must be a valid IAM role ARN for AWS_ACCOUNT_ID and must
differ from the monitoring role. Missing or invalid execution roles block both
preview eligibility and execution; execution never falls back to host credentials.

The worker waits up to five minutes for the instance_stopped waiter. A timeout is an
unconfirmed outcome: AWS may have accepted the stop. Check the console or a new scan
before taking further action. The worker never automatically retries a live stop.
A unique constraint permits one execution per recommendation, including failures.
This conservative MVP limitation prevents duplicate actions but requires manual
review before any retry/reset workflow. No automated rollback is claimed.

RDS resizing remains an explicit, reviewed Terraform operation. The application never
generates unrestricted commands from Claude output.

## Scheduling and notifications

Local mode runs a timer in one API process. Run only one API worker in local mode.
Celery mode uses one Beat process and the database's active-scan constraint.
Default scheduling and notification preferences are off; enable in Settings.
Notifications are persisted even when delivery is off. Enabling delivery sends pending
events at the next delivery cycle. Uncertain/failed deliveries are recorded, not retried.

## External verification still needed

The delivered demo was tested locally. Validate AWS permissions, model availability,
SES sandbox status, Slack delivery, PostgreSQL/Redis startup and deployed HTTPS in your
environment before relying on those external paths. No cloud resources were created.

## Source documentation

- https://docs.aws.amazon.com/boto3/latest/reference/services/cloudwatch/client/get_metric_statistics.html
- https://docs.aws.amazon.com/boto3/latest/reference/services/ec2/client/stop_instances.html
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs

Local infrastructure check: Terraform init, formatting and validate passed on October 11, 2026. No infrastructure was applied. Docker verification is provided through scripts/verify-compose.py; this session cannot access the Docker engine named pipe. See live-setup.md for configuration and verification steps.
