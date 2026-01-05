import time
from datetime import datetime, timezone
from django.urls import resolve
from tracelet.core.engine import Engine, get_engine

class DjangoMiddleware:
    def __init__(self, get_response, engine: Engine = None):
        self.get_response = get_response
        self.framework = "django"
        self.engine = engine or get_engine()

    def __call__(self, request):
        start_perf = time.perf_counter()
        start_dt = datetime.now(timezone.utc)

        response = self.get_response(request)

        elapsed = time.perf_counter() - start_perf
        
        # Path Normalization
        route = getattr(request, 'resolver_match', None)
        if not route:
            try:
                route = resolve(request.path_info)
            except:
                route = None

        path = route.route if route else request.path

        data = {
            "api_url": path,
            "start_dt": start_dt,
            "end_dt": datetime.now(timezone.utc),
            "elapsed": elapsed,
            "response_status": response.status_code,
            "framework": self.framework
        }

        self.engine.capture(data)

        return response