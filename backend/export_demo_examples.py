"""Export real API response examples using a disposable database, never the user's DB."""
import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

with tempfile.TemporaryDirectory(prefix='optimizer-examples-') as temporary:
    os.environ['DATABASE_URL'] = 'sqlite:///' + (Path(temporary) / 'demo.db').as_posix()
    os.environ['JOB_MODE'] = 'local'
    os.environ['EXPLANATION_MODE'] = 'mock'
    os.environ['ADAPTER_MODULE'] = 'app.services.mock_provider'
    from fastapi.testclient import TestClient
    from app.database import Base, engine
    from app.main import app
    try:
        Base.metadata.create_all(engine)
        with TestClient(app) as client:
            scan = client.post('/api/v1/scans')
            assert scan.status_code == 202, scan.text
            examples = {'scan_created': scan.json()}
            for name, path in [('scan_completed', '/scans/' + scan.json()['id']),
                               ('resources', '/resources'), ('recommendations', '/recommendations'),
                               ('overview', '/overview')]:
                response = client.get('/api/v1' + path)
                response.raise_for_status()
                examples[name] = response.json()
            rec = next(r for r in examples['recommendations']['items'] if r['finding_type'] == 'idle_ec2')
            path = '/api/v1/recommendations/' + rec['id']
            request = {'idempotency_key': str(uuid4())}
            examples['approval_error'] = client.post(path + '/execute', json=request).json()
            examples['approved'] = client.post(path + '/approve').json()
            job = client.post(path + '/execute', json=request).json()
            examples['execution_request'] = request
            examples['execution_created'] = job
            examples['execution_completed'] = client.get('/api/v1/executions/' + job['id']).json()
            examples['executions'] = client.get('/api/v1/executions').json()
        destination = Path(__file__).resolve().parents[1] / 'contracts' / 'examples.json'
        destination.write_text(json.dumps(examples, indent=2), encoding='utf-8')
        print('Exported contracts/examples.json from an isolated mock API run.')
    finally:
        engine.dispose()
