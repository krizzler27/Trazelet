from concurrent.futures import ThreadPoolExecutor
from tracelet.config import settings
from tracelet.logger_config import logger

class AsyncWorker:
    def __init__(self):
            max_workers = getattr(settings, 'max_workers', 1) or 1
            self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def queue_task(self, task_func, *args):
        """Submit a task to the background."""
        try:
            self._executor.submit(task_func, *args)
        except Exception as e:
            logger.error("Unexpected error while submitting task to executor: %s", e, exc_info=True)

    def stop(self):
        """Graceful shutdown - waits for all tasks to complete, then shuts down executor."""
        try:
            self._executor.shutdown(wait=True)
        except Exception as e:
            logger.error("Error while shutting down Thread worker: %s", e, exc_info=True)