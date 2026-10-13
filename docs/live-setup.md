# Live setup — personal AWS account, Mumbai

Run commands from the repository root unless stated otherwise. Configure one integration
at a time and restart after changes. Secrets belong in your terminal and ignored local
configuration files, never in Git or screenshots.

## 1. AWS credentials and read-only collection

Install AWS CLI v2 using the official Windows installer:
https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
Open a new PowerShell and check `aws --version`.

Prefer a temporary-credential/SSO profile where your account supports it:
`aws configure sso --profile optimizer`, then `aws sso login --profile optimizer`.
If using an IAM user for a personal lab, configure its access key locally with
`aws configure --profile optimizer`. Set region to `ap-south-1`, output to `json`.
Do not use root access keys. The monitoring identity only needs the actions listed
in `infra/monitor-policy.json`; it does not need AdministratorAccess.

Verify your profile:

```powershell
aws sts get-caller-identity --profile optimizer
backend\.venv\Scripts\python.exe scripts\configure-integrations.py aws
cd backend
.venv\Scripts\python.exe -m alembic upgrade head
cd ..
.\start-project.ps1
```

The setup assistant checks the AWS identity, selects Mumbai by default, stores only
the profile name/role configuration, and selects a separate SQLite database for the
account. It does not copy access keys. The new database bootstraps from the existing
ADMIN_PASSWORD value; changing a demo database password does not change that value.
Existing demo data is preserved. Live execution remains off.

In Settings, validate the connection; then run a scan. Cost Explorer must be enabled
and usable by the account. An account without resources may correctly return an empty
inventory. An instance needs sustained CloudWatch evidence before the idle rule can
recommend stopping it: at least seven days and 168 hourly samples. Do not fabricate
live history to demonstrate an immediate recommendation; use demo mode for that.

Public prices support shared-tenancy Linux/UNIX and Windows On-Demand EC2 only.
Spot, Marketplace/licensed images and dedicated tenancy remain unpriced. Savings use
730 compute hours and exclude storage, IP charges, discounts and commitments.

## 2. Separate execution role and Terraform

Use the `infra` module to provision monitoring/execution roles. Supply a trusted IAM
principal ARN and external ID in an ignored `infra/terraform.tfvars` file. Keep
`create_demo_instance=false` unless you intentionally want a new billable resource.
Review `terraform plan` before `terraform apply` using a separate provisioning identity.
The local monitoring identity additionally needs permission to assume the two roles;
role trust alone does not grant caller-side AssumeRole permissions.

Run the AWS setup assistant again with both returned role ARNs. Only after checking
the target instance, enable `LIVE_EXECUTION_ENABLED=true` locally and restart. EC2
stops require `optimizer:managed=true`, `Environment=demo`, and EBS-backed storage.

Approve a fresh idle recommendation. Choose either dashboard execution or Terraform
export. The dashboard waits up to five minutes for a stopped state. A timeout can mean
AWS accepted the request; inspect AWS before taking further action.

The Terraform export has a one-hour expiry, checks tags and the connected account,
and controls only instance power state. Follow its on-screen instructions, preserve
the state and lock file, and run a new scan after applying. Exporting does not apply
the change and cannot be claimed as a completed execution.

## 3. Claude

Create an API key in your Anthropic console, ensure API access is funded/available,
and select a model ID available to your account with structured-output support.
Do not assume a chat subscription includes API usage.

```powershell
backend\.venv\Scripts\python.exe scripts\configure-integrations.py claude
```

Restart and scan new findings. Their detail page should show “Claude explanation”.
Fallback explanations remain available if the model call fails. Existing findings
retain their prior explanation; use a new finding/database for first-time verification.
Reference: https://platform.claude.com/docs/en/build-with-claude/structured-outputs

## 4. Slack and email

Create a Slack app with Incoming Webhooks, authorize a dedicated demo channel, and
copy its webhook into the hidden prompt:

```powershell
backend\.venv\Scripts\python.exe scripts\configure-integrations.py slack
```

For email, verify the sender identity in SES in Mumbai. In the SES sandbox, also verify
the recipient. Grant the runtime identity permission to send from that SES identity.

```powershell
backend\.venv\Scripts\python.exe scripts\configure-integrations.py email
```

Restart, enable Critical notifications in Settings, then scan a high-risk finding.
Enabling delivery also processes pending events. Check Notification activity AND the
destination channel/mailbox. Failed/uncertain deliveries do not automatically retry.
References: https://api.slack.com/messaging/webhooks and
https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html

## 5. Docker verification

With Docker Desktop running, execute:

```powershell
backend\.venv\Scripts\python.exe scripts\verify-compose.py
```

Leave port 15173 available. This creates an isolated mock stack, checks PostgreSQL,
Celery scan/execution, the frontend proxy and restart persistence, then removes its
own containers and volumes. It never connects to AWS or uses the normal database.

The ordinary Compose stack uses the root PostgreSQL password and backend/.env. For
live Docker deployments, a Windows AWS profile is not automatically available inside
containers. Use a workload role on the host or explicitly provide a compatible
read-only credentials mount. Leave AWS_PROFILE empty when using workload credentials.

## 6. Hosted deployment

Choose a Linux host and DNS name first. No host, domain or paid resource has been
created by these changes. Point the DNS name to the host; allow inbound TCP 80/443.
Keep database, Redis, API and frontend ports private (base Compose binds HTTP locally).

Generate local configuration with setup_demo.py and setup-compose.py, set APP_DOMAIN
in root .env, and set CORS_ORIGINS to the HTTPS site origin. Keep AUTH_ENABLED=true.

```sh
docker compose -f docker-compose.yml -f compose.production.yml up -d --build
```

Caddy provides the HTTPS entry point. Check login, readiness and a scan through the
public hostname. Restart the stack and confirm data persists. Back up PostgreSQL with
pg_dump and test restoring into a separate database before relying on the deployment.
Do not run `docker compose down --volumes` against the real stack.

## 7. Reviewed RDS resizing

RDS findings are capacity-review candidates, not validated sizing decisions. Confirm
engine compatibility, workload peaks, memory, backups and the maintenance window.
The database must already be managed by Terraform and tagged as an optimizer demo.
This project deliberately does not import or recreate an arbitrary existing database.

Use an existing root Terraform variable that controls only the selected instance class:

```powershell
backend\.venv\Scripts\python.exe scripts\plan-rds.py --directory C:\path\to\existing-terraform --address aws_db_instance.demo --identifier demo-db --variable db_instance_class --target-class db.t3.medium
```

The target above is an example, not a sizing recommendation. The validator accepts
exactly one in-place class update, with backups and deletion protection already enabled,
and apply_immediately=false. It rejects additional resource changes and replacements.
Review the private saved plan and review.json; apply that exact plan only after review.
Run a new scan after the maintenance window. A saved plan is not proof of a resized DB.
