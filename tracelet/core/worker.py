from concurrent.futures import ThreadPoolExecutor
import atexit

class AsyncWorker:
    def __init__(self, max_workers=1):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        # Ensure cleanup happens
        atexit.register(self.stop)

    def queue_task(self, task_func, *args):
        """Submit a task to the background."""
        self._executor.submit(task_func, *args)

    def stop(self):
        """Graceful shutdown."""
        self._executor.shutdown(wait=True, cancel_futures=True)