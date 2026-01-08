from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import time
from datetime import datetime, timezone
from tracelet.core.engine import _Engine, get_engine
from tracelet.utils.logger_config import logger

class FastAPIMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, engine: _Engine = None):
        super().__init__(app)
        self.engine = engine or get_engine()
        self.framework = "fastapi"

    async def dispatch(self, request: Request, call_next):

        try:
            start_perf = time.perf_counter()
            start_dt = datetime.now(timezone.utc)

            response = await call_next(request)

            elapsed = time.perf_counter() - start_perf
            
            # Get path --- Normalization ---
            route = request.scope.get("route")
            path = route.path if route and hasattr(route, "path") else request.url.path

            data = {
                "path": path,
                "start_dt": start_dt,
                "end_dt": datetime.now(timezone.utc),
                "elapsed": elapsed,
                "response_status": response.status_code,
                "framework": self.framework,
            }

            # Offload capture work to background thread to keep request path lightweight
            self.engine.worker.queue_task(self.engine.capture, data)
        
        except Exception as e:
            logger.error("Unexpected error in FastAPI Middleware: %s", e, exc_info=True)

        return response