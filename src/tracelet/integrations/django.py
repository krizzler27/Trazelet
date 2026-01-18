import time
from datetime import datetime, timezone
from django.urls import resolve
from tracelet.core.engine import _Engine, get_engine
from tracelet.utils.logger_config import logger


class DjangoMiddleware:
    def __init__(self, get_response, engine: _Engine = None):
        self.get_response = get_response
        self.framework = "django"
        self.engine = engine or get_engine()

    def __call__(self, request):
        try:
            start_perf = time.perf_counter()
            start_dt = datetime.now(timezone.utc)

            response = self.get_response(request)

            elapsed = time.perf_counter() - start_perf

            #  --- Path Normalization ---
            route = getattr(request, "resolver_match", None)
            if not route:
                try:
                    route = resolve(request.path_info)
                except:
                    route = None

            path = route.route if route else request.path

            data = {
                "path": path,
                "method": request.method,
                "start_dt": start_dt,
                "end_dt": datetime.now(timezone.utc),
                "elapsed": elapsed,
                "response_status": response.status_code,
                "framework": self.framework,
            }

            # Offload capture work to background thread to keep request path lightweight
            self.engine.worker.queue_task(self.engine.capture, data)
        except Exception as e:
            logger.error("Unexpected error in Django Middleware: %s", e, exc_info=True)

        return response
