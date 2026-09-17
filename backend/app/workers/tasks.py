from app.workers.celery_app import celery_app

@celery_app.task(name='optimizer.scan')
def scan_task(job_id):
    from app.services.jobs import run_scan
    run_scan(job_id)

@celery_app.task(name='optimizer.execute')
def execute_task(job_id):
    from app.services.jobs import run_execution
    run_execution(job_id)

