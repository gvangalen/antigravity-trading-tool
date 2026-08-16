from celery import shared_task

from backend.utils.openai_client import probe_openai_runtime


@shared_task(name="backend.celery_task.system_task.probe_openai_runtime")
def probe_openai_runtime_task():
    return probe_openai_runtime(caller="celery_worker")
