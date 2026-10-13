# Cloudwise — Intelligent Cloud Infrastructure Optimizer

A three-person university capstone, integrated into one runnable application.
React/TypeScript dashboard, FastAPI, SQLAlchemy/Alembic, PostgreSQL, Celery/Redis,
Boto3, optional Claude explanations, and Terraform infrastructure.

## Try the complete demo

Run the commands below from the repository root (Python 3.12 and Node 24 required).
A local administrator password is generated in backend/.env. It is not committed.

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python.exe backend/setup_demo.py
corepack enable
corepack pnpm --dir frontend install --frozen-lockfile
corepack pnpm --dir frontend build
cd backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Username: admin. Password: ADMIN_PASSWORD in backend/.env.
The same server serves the frontend production build and API.
Do not recreate an existing virtual environment unnecessarily.

Alternatively use the root start-project.ps1 script in PowerShell. It locates the
bundled Codex runtime if Node/pnpm are not installed on your PATH.

## What works

- Administrator login, hashed passwords, expiring/revocable bearer sessions.
- Password changes in Settings, with current-password verification and all-session revocation.
- Dashboard with spending history, savings estimates, resource inventory and details.
- Mock EC2/RDS collectors aligned with shared contracts; missing data is explicit.
- Idle EC2, RDS capacity-review, and daily cost anomaly recommendations.
- Approval, preview, idempotent execution, execution history and audit API.
- Simulated EC2 stops with eligibility and freshness checks.
- Read-only AWS collector using credential chain or AssumeRole, pagination and CloudWatch.
- Optional live EC2 stop: disabled by default, separate execution role and demo tags required.
- Optional Claude structured explanations with validated output and fallback.
- Scheduled scans, daily billing cache, opt-in Slack/SES notification delivery.
- Docker Compose: PostgreSQL, Redis, migration job, backend, worker, Beat, frontend.
- Terraform IAM roles and an opt-in demo EC2 instance; nothing is provisioned automatically.
- Backend and browser tests, generated contracts and CI workflows.

## Boundaries

The complete demo works without cloud keys. Real AWS/Claude/Slack/SES require your
accounts and configuration and must be validated in a sandbox.
Live RDS resizing is not automated: RDS recommendations are advisory, with a separately
reviewed Terraform workflow. No savings are described as realized without billing evidence.
The AWS collector uses public On-Demand prices for supported EC2 configurations;
unsupported or unavailable prices remain explicit. Estimates are not effective bill savings.

Default local mode uses SQLite and in-process background work for easy review.
Use PostgreSQL/Celery for persistent deployments. Local interrupted jobs require manual
recovery with backend/recover_demo_jobs.py after all workers stop.

## Docker stack

```powershell
backend/.venv/Scripts/python.exe backend/setup_demo.py
backend/.venv/Scripts/python.exe scripts/setup-compose.py
docker compose up --build
```

Open http://127.0.0.1:5173. API docs: http://127.0.0.1:8000/docs.
Ports are bound to loopback. Avoid conflicting local servers on those ports.
Database password is generated into root .env; never commit it.

## Development

Backend: see backend/README.md and docs/configuration.md.
Frontend: `corepack pnpm --dir frontend dev` (backend on port 8000).
Authentication tokens are scoped to the browser session. Signing out revokes the session.
API docs include the Authorize button for bearer tokens returned by /auth/login.

```powershell
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
cd backend
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe export_contracts.py
cd ../frontend
corepack pnpm build
corepack pnpm test
```

Browser tests expect a running app, backend/.env, and Edge on Windows.
On Linux install Chromium with `pnpm exec playwright install --with-deps chromium`.
The browser workflow uses the demo account and creates scan/execution records.

Run `backend/.venv/Scripts/python.exe scripts/test-security.py` from the repository
root to test password changes with a disposable database and account. Build the
frontend first and leave port 8012 available. Node must be on PATH or specified
through NODE_EXECUTABLE. This test does not change your existing administrator password.

## Repository ownership

- backend/app/cloud + backend/app/remediation + infra: cloud integration.
- backend/app/api + services + workers + models: backend and intelligence.
- frontend + docker-compose.yml + .github/workflows: dashboard and delivery.

See docs/demo-checklist.md for the capstone walkthrough.

## Live setup and submission

See docs/live-setup.md for AWS Mumbai, Claude, alerts, Docker and HTTPS deployment.
Interactive local configuration: `python scripts/configure-integrations.py aws`
(or claude, slack, email), using your backend virtual environment.
Approved EC2 recommendations offer a Terraform export. Existing Terraform-managed
RDS databases can use scripts/plan-rds.py for a checked maintenance-window plan.
The architecture, report draft and presentation outline are in docs/capstone-report.md.
