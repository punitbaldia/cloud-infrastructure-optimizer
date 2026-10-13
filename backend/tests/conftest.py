import os
import tempfile
from pathlib import Path
import pytest

TEST_ROOT = Path(__file__).resolve().parents[2] / 'work' / 'tests'
TEST_ROOT.mkdir(parents=True, exist_ok=True)
TEST_DIR = tempfile.TemporaryDirectory(prefix='optimizer-tests-', dir=TEST_ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///' + (Path(TEST_DIR.name)/'test.db').as_posix()
os.environ['JOB_MODE'] = 'local'
os.environ['AUTH_ENABLED'] = 'false'
os.environ['EXPLANATION_MODE'] = 'mock'
os.environ['ADAPTER_MODULE'] = 'app.services.mock_provider'
os.environ['CLOUD_MODE'] = 'mock'
os.environ['AWS_ACCOUNT_ID'] = '000000000000'
os.environ['AWS_REGION'] = 'ap-south-1'
os.environ['AWS_PROFILE'] = ''
os.environ['LIVE_EXECUTION_ENABLED'] = 'false'
os.environ['SLACK_WEBHOOK_URL'] = ''
os.environ['SES_SENDER'] = ''
os.environ['ALERT_RECIPIENT'] = ''

from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app

@pytest.fixture(scope='session', autouse=True)
def cleanup_database():
    yield
    engine.dispose()
    TEST_DIR.cleanup()

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        yield client
