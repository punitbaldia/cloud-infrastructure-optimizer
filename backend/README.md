# Backend

The backend is integrated with the React dashboard. Start from the repository
README for the full application setup.

Default: authenticated local demo, SQLite, in-process background jobs, compatible
mock cloud adapter. PostgreSQL/Celery/Redis are configured by root Docker Compose.

## Setup

From backend:
```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe setup_demo.py
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Generate the frontend build first to serve the dashboard from this server.
Otherwise API docs remain at /docs. Use /api/v1/auth/login and its access_token
with the Swagger Authorize control.

## Checks

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe export_contracts.py
.venv/Scripts/python.exe export_demo_examples.py
```

Tests run in a separate temporary database without AWS/Claude calls.
Fixtures in app/cloud/mock.py now match app/schemas.py.
app/services/mock_provider.py remains only as a backwards-compatible fixture source.

## Operations

- POST /scans queues a collection, analysis and notification-event pass.
- Costs are fetched at most once per UTC day.
- Settings control periodic collection and opt-in notifications.
- POST /api/v1/auth/password verifies the current password and revokes all sessions after rotation.
- Live EC2 execution requires a separate execution role in the configured AWS account.
- A fresh scan invalidates approval when refreshing an unexecuted recommendation.
- Each recommendation has at most one execution; repeated keys return the same job.
- All external actions require server configuration; demo execution never contacts AWS.
- RDS recommendations are advisory, not automatic resize decisions.
- Missing prices return unavailable savings, never an AI-generated amount.
- Failed delivery status is visible in Settings.
- recover_demo_jobs.py is only for recovery with all workers stopped.

Full configuration and limitations: ../docs/configuration.md.
