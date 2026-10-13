# Local capstone demonstration — no paid services

Deployment is deferred. You do not need a domain, hosting plan, AWS resources or a
Claude API key to demonstrate the implemented workflow. Use mock mode and accurately
label rule-based explanations and simulated actions when presenting.

## Start

From the repository root in PowerShell:

```powershell
.\start-project.ps1
```

Open http://127.0.0.1:8001 and sign in with the existing administrator account.
The initial password is stored only in backend/.env; if you changed it in Settings,
use the changed password for that database.

If you previously enabled AWS mode, use a separate mock database and these settings
in backend/.env before starting: CLOUD_MODE=mock, EXPLANATION_MODE=mock,
ADAPTER_MODULE=app.cloud.mock, LIVE_EXECUTION_ENABLED=false,
AWS_ACCOUNT_ID=000000000000, AWS_REGION=ap-south-1. Leave scheduling and notifications
off for the presentation. Do not point mock mode at an existing live database.

## Seven-minute walkthrough

1. Explain the problem and architecture from docs/capstone-report.md.
2. Sign in, run a scan and show the overview. Identify costs as synthetic demo data.
3. Open Resources and inspect EC2 utilization and RDS metrics.
4. Open an idle EC2 recommendation; discuss evidence, medium risk and savings assumptions.
5. Approve it and prepare/download the Terraform demo artifact. It contains no AWS action.
6. Run the simulated execution and show its history and audit API record.
7. Show database review and cost-anomaly findings, then Settings and account security.

Use a fresh demo database for a repeatable demonstration: the application deliberately
allows only one execution per recommendation. Do not erase the previous database;
choose a new SQLite filename through DATABASE_URL and rerun migrations.

## Verification in your PowerShell

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
cd ..
backend\.venv\Scripts\python.exe scripts\test-security.py --workflow
backend\.venv\Scripts\python.exe scripts\test-security.py
backend\.venv\Scripts\python.exe scripts\verify-compose.py
```

Install requirements-dev.txt into the backend environment if pytest is missing.
Browser checks require Node on PATH (or NODE_EXECUTABLE), a built frontend and Edge on
Windows. They use a disposable database and never rotate your real password. The Docker
check requires Docker Desktop and a free port 15173. It removes only its test stack.

## What is and is not demonstrated

The local demo demonstrates collection contracts, rules, UI, authentication, approval,
simulation, audit records and infrastructure plan generation. It does not prove live AWS
permissions, actual Claude responses, real alert delivery, real cost savings or hosted
availability. The optional integration code and setup guide remain ready for later
account configuration and testing; no paid resource is required for this walkthrough.
