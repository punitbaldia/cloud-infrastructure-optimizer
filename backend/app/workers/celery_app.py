from celery import Celery
from app.config import get_settings

settings = get_settings()
celery_app = Celery('optimizer', broker=settings.redis_url, include=['app.workers.tasks'])
celery_app.conf.update(task_serializer='json', accept_content=['json'], timezone='UTC',
                       broker_connection_retry_on_startup=True,
                       task_soft_time_limit=180, task_time_limit=210,
                       task_publish_retry=False, broker_connection_timeout=3)

