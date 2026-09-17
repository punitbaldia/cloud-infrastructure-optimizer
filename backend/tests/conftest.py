import os
import tempfile
from pathlib import Path
import pytest

TEST_DIR = tempfile.TemporaryDirectory(prefix='optimizer-tests-')
os.environ['DATABASE_URL'] = 'sqlite:///' + (Path(TEST_DIR.name)/'test.db').as_posix()
os.environ['JOB_MODE'] = 'local'
os.environ['EXPLANATION_MODE'] = 'mock'
os.environ['ADAPTER_MODULE'] = 'app.services.mock_provider'

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
