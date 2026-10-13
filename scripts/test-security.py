"""Run password UI checks against an isolated, disposable account. Requires frontend build."""
import os
import argparse
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--workflow', action='store_true', help='Test the full demo workflow instead of password changes')
args = parser.parse_args()
work = root / 'work'
work.mkdir(exist_ok=True)
node = os.environ.get('NODE_EXECUTABLE') or shutil.which('node')
if not node:
    raise SystemExit('Set NODE_EXECUTABLE or install Node.js on PATH.')
with tempfile.TemporaryDirectory(prefix='security-browser-', dir=work) as directory:
    temporary = Path(directory)
    env = {**os.environ, 'DATABASE_URL': 'sqlite:///' + (temporary / 'test.db').as_posix(),
           'AUTH_ENABLED': 'true', 'ADMIN_USERNAME': 'admin', 'ADMIN_PASSWORD': secrets.token_urlsafe(24),
           'CLOUD_MODE': 'mock', 'JOB_MODE': 'local', 'EXPLANATION_MODE': 'mock',
           'AWS_ACCOUNT_ID': '000000000000', 'AWS_REGION': 'ap-south-1', 'AWS_PROFILE': '',
           'ADAPTER_MODULE': 'app.cloud.mock', 'LIVE_EXECUTION_ENABLED': 'false',
           'SLACK_WEBHOOK_URL': '', 'SES_SENDER': '', 'ALERT_RECIPIENT': ''}
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=root / 'backend', env=env, check=True)
    with (temporary / 'server.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8012'],
                                  cwd=root / 'backend', env=env, stdout=log, stderr=log)
        try:
            for _ in range(50):
                if server.poll() is not None:
                    raise RuntimeError('Test server failed to start; check whether port 8012 is occupied.')
                try:
                    urllib.request.urlopen('http://127.0.0.1:8012/api/v1/health', timeout=1).close()
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError('Test server did not become ready.')
            env.update({'TEST_BASE_URL': 'http://127.0.0.1:8012', 'SECURITY_TEST_PASSWORD': env['ADMIN_PASSWORD'], 'TEST_ADMIN_PASSWORD': env['ADMIN_PASSWORD']})
            subprocess.run([node, 'node_modules/@playwright/test/cli.js', 'test', 'tests/workflow.spec.ts' if args.workflow else 'tests/security.spec.ts'],
                           cwd=root / 'frontend', env=env, check=True)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
