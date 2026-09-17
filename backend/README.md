# Person 2 backend

This is a local mock-first milestone, not a production cloud controller.
No AWS credentials are required. All execution is simulated, even if a replacement
collector is configured. Authentication, notifications, live AWS integration, RDS
rightsizing and Terraform execution are not implemented here.

## Quick start (PowerShell, inside backend)

Stop the previous server with Ctrl+C first.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Default mode uses backend/demo.db (SQLite) and FastAPI background tasks.
No .env is required. GET /api/v1/health checks the app; /ready checks DB connectivity.
Swagger UI: http://127.0.0.1:8000/docs

SQLite is a local testing fallback, not a replacement for the selected PostgreSQL stack.
Local jobs are not durable: stopping the process during a job can leave it running.
Use the recovery script below only after stopping the API and workers.

## PostgreSQL and Celery

Person 3 owns the root Docker Compose. compose.backend.yml is an independent dev helper.

```powershell
docker compose -f compose.backend.yml up -d
$env:DATABASE_URL = 'postgresql+psycopg://optimizer:optimizer_dev@localhost:5433/optimizer'
$env:JOB_MODE = 'celery'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, set the same DATABASE_URL and JOB_MODE, then run:

```powershell
.\.venv\Scripts\python.exe -m celery -A app.workers.celery_app:celery_app worker --pool=solo --loglevel=info
```

Windows solo pool is for development; Person 3 should run a Linux worker for deployment.
Redis uses localhost:6379. Changing database URL does not copy SQLite data.
Run migrations before starting API/worker. No periodic Beat schedule is registered yet.

## Manual verification

1. GET /overview: empty database returns zero counts.
2. POST /scans (no body); copy returned id.
3. GET /scans/{id} until succeeded.
4. GET /resources: four fixtures (idle EC2, active EC2, RDS, missing metrics).
5. GET /recommendations: idle EC2 plus daily cost anomaly.
6. Copy the idle EC2 recommendation id.
7. POST /recommendations/{id}/execute before approval: HTTP 409.
8. POST /recommendations/{id}/approve (no body or {}).
9. POST /recommendations/{id}/execute with:
   {"idempotency_key":"8d611737-347f-45b9-9f74-cd1777e26126"}
10. GET /executions/{id}: succeeded, simulated=true.
11. Repeat execution: same job; no duplicated simulation.
12. Restart API: records remain in the configured database.

Base path for every endpoint above: /api/v1.
Estimated idle compute savings are 14.60 USD based on a deliberately synthetic price.
Observed savings remain null. A simulated success does not resolve the real finding.
Cost data includes fifteen completed fixture days, not necessarily a whole month.

## Rules and limitations

Idle EC2 requires at least seven days, 168 samples for each metric, maximum CPU below
5%, maximum network below 1,000,000 Bytes/hour, running state, and complete data.
Metric keys/units/aggregations are fixed in the contracts. Missing values fail eligibility.
Execution additionally requires optimizer:managed=true and fresh observations/recommendations.
Thresholds are demo defaults in services/rules.py, not validated production policies.
RDS is inventory-only until sufficient evidence and pricing logic are implemented.

Cost anomaly requires fourteen consecutive completed baseline days, a positive baseline,
at least 2x average and at least 5 currency units above average. Target day is excluded.
Estimated billing days are excluded from anomaly detection.
One resource recommendation per resource is kept; existing explanations are reused.
Re-evaluation/versioning of changed recommendations is future work. Worker rechecks current
eligibility before simulation, and recommendations expire after 24 hours for execution.
One execution per recommendation is enforced, including failed executions; automatic retry is
intentionally not implemented. Freshness/eligibility failure requires a reviewed recovery flow.

## Claude (optional)

Default explanation mode is mock. In backend/.env set EXPLANATION_MODE=claude,
ANTHROPIC_API_KEY and a supported CLAUDE_MODEL from your Anthropic account.
New findings request schema-validated text; failures fall back to rule explanations.
Existing findings reuse their explanation. No actual Claude request is required by tests.
SDK guide: https://platform.claude.com/docs/en/build-with-claude/structured-outputs

## Tests and contracts

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe export_contracts.py
```

Tests use an isolated temporary SQLite database and do not contact AWS/Claude.
requirements.txt defines compatibility ranges; requirements-lock.txt captures the tested
environment, including development tools, for reproducibility.

## Recover abandoned demo jobs

Stop every API/worker process, then:

```powershell
.\.venv\Scripts\python.exe recover_demo_jobs.py
```

This marks queued/running jobs failed and releases the active scan slot; it never reruns
an action. Do not run it while workers are active.

## Security and integration boundary

No login or per-user authorization exists in this local milestone. Bind to loopback only.
CORS allows local Vite origins. Keep all .env files and demo databases out of Git.
Never use this build as an exposed or production service.

