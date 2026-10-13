"""Build and verify an isolated Docker demo; never uses real cloud keys or the normal database."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.request
import uuid

root = Path(__file__).resolve().parents[1]
project = 'optimizer-check-' + uuid.uuid4().hex[:8]
work = root / 'work'
work.mkdir(exist_ok=True)
password = secrets.token_urlsafe(24)
env = {**os.environ, 'CHECK_DB_PASSWORD': secrets.token_hex(24), 'CHECK_ADMIN_PASSWORD': password}
backend_env = {'DATABASE_URL': 'postgresql+psycopg://optimizer:${CHECK_DB_PASSWORD}@postgres:5432/optimizer',
               'REDIS_URL': 'redis://redis:6379/0', 'JOB_MODE': 'celery', 'AUTH_ENABLED': 'true',
               'ADMIN_USERNAME': 'admin', 'ADMIN_PASSWORD': '${CHECK_ADMIN_PASSWORD}',
               'CLOUD_MODE': 'mock', 'ADAPTER_MODULE': 'app.cloud.mock', 'EXPLANATION_MODE': 'mock',
               'LIVE_EXECUTION_ENABLED': 'false'}
backend = {'build': str(root / 'backend'), 'environment': backend_env}
services = {
    'postgres': {'image': 'postgres:16-alpine', 'environment': {'POSTGRES_USER': 'optimizer', 'POSTGRES_DB': 'optimizer', 'POSTGRES_PASSWORD': '${CHECK_DB_PASSWORD}'},
                 'volumes': ['check_db:/var/lib/postgresql/data'],
                 'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U optimizer -d optimizer'], 'interval': '3s', 'retries': 30}},
    'redis': {'image': 'redis:7-alpine', 'healthcheck': {'test': ['CMD', 'redis-cli', 'ping'], 'interval': '3s', 'retries': 30}},
    'migrate': {**backend, 'command': 'python -m alembic upgrade head', 'depends_on': {'postgres': {'condition': 'service_healthy'}}},
    'backend': {**backend, 'command': 'python -m uvicorn app.main:app --host 0.0.0.0 --port 8000',
                'depends_on': {'migrate': {'condition': 'service_completed_successfully'}, 'redis': {'condition': 'service_healthy'}},
                'healthcheck': {'test': ['CMD', 'python', '-c', "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/ready')"], 'interval': '3s', 'retries': 30}},
    'worker': {**backend, 'command': 'celery -A app.workers.celery_app:celery_app worker --loglevel=warning',
               'depends_on': {'backend': {'condition': 'service_healthy'}}},
    'beat': {**backend, 'command': 'celery -A app.workers.celery_app:celery_app beat --loglevel=warning',
             'depends_on': {'backend': {'condition': 'service_healthy'}}},
    'frontend': {'build': str(root / 'frontend'), 'ports': ['127.0.0.1:15173:80'], 'depends_on': {'backend': {'condition': 'service_healthy'}}},
}
token = None


def api(path, body=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request('http://127.0.0.1:15173/api/v1' + path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def finished(path):
    for _ in range(90):
        result = api(path)
        if result['status'] == 'succeeded':
            return result
        if result['status'] == 'failed':
            raise RuntimeError(result['message'])
        time.sleep(1)
    raise RuntimeError('Background job did not finish within 90 seconds.')


with tempfile.TemporaryDirectory(prefix='compose-check-', dir=work) as folder:
    config = Path(folder) / 'compose.json'
    config.write_text(json.dumps({'services': services, 'volumes': {'check_db': {}}}), encoding='utf-8')
    command = ['docker', 'compose', '-p', project, '-f', str(config)]
    def compose(*args):
        subprocess.run([*command, *args], env=env, check=True)
    try:
        print('Building isolated demo on http://127.0.0.1:15173. First build can take several minutes.', flush=True)
        compose('up', '-d', '--build', '--wait', '--wait-timeout', '180')
        token = api('/auth/login', {'username': 'admin', 'password': password})['access_token']
        scan = api('/scans', {})
        finished('/scans/' + scan['id'])
        assert api('/resources')['total'] == 4
        recommendations = api('/recommendations')['items']
        assert {r['finding_type'] for r in recommendations} == {'idle_ec2', 'oversized_rds', 'cost_anomaly'}
        rec = next(r for r in recommendations if r['proposed_action'] == 'stop_ec2')
        path = '/recommendations/' + rec['id']
        api(path + '/approve', {})
        assert api(path + '/terraform', {})['simulated']
        job = api(path + '/execute', {'idempotency_key': str(uuid.uuid4())})
        assert finished('/executions/' + job['id'])['simulated']
        compose('restart', 'backend', 'worker')
        for _ in range(60):
            try:
                assert api('/resources')['total'] == 4
                break
            except (OSError, AssertionError):
                time.sleep(1)
        else:
            raise RuntimeError('Persistence/restart check failed.')
        assert api('/executions/' + job['id'])['status'] == 'succeeded'
        print('PASS: PostgreSQL migrations, Redis/Celery scan and execution, frontend proxy, Terraform demo export, and restart persistence.', flush=True)
    finally:
        # Only this randomly named test project and its test database are removed.
        subprocess.run([*command, 'down', '--volumes', '--remove-orphans'], env=env, check=False)
