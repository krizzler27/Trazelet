from concurrent.futures import ThreadPoolExecutor
from tracelet.config import settings
import atexit

class AsyncWorker:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=settings.max_workers)

    def queue_task(self, task_func, *args):
        """Submit a task to the background."""
        self._executor.submit(task_func, *args)

    def stop(self):
        """Graceful shutdown - waits for all tasks to complete, then shuts down executor."""
        self._executor.shutdown(wait=True)