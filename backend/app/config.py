from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND / '.env'), extra='ignore')
    database_url: str = 'sqlite:///' + (BACKEND / 'demo.db').as_posix()
    job_mode: Literal['local', 'celery'] = 'local'
    redis_url: str = 'redis://localhost:6379/0'
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'
    explanation_mode: Literal['mock', 'claude'] = 'mock'
    anthropic_api_key: str = ''
    claude_model: str = ''
    adapter_module: str = 'app.services.mock_provider'
    recommendation_ttl_hours: int = 24


@lru_cache
def get_settings():
    return Settings()
