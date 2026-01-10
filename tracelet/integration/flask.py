import time
from datetime import datetime, timezone
from flask import request, g
from tracelet.core.engine import _Engine, get_engine
from tracelet.utils.logger_config import logger


class FlaskMiddleware:
    def __init__(self, app=None, engine: _Engine = None):
        self.engine = engine or get_engine()
        self.framework = "flask"
        if app:
            self.init_app(app)

    def init_app(self, app):
        app.before_request(self._before_request)
        app.after_request(self._after_request)

    def _before_request(self):
        # We put these on the 'Tray' (g) because this function 
        # will end before the response is ready.
        g._tracelet_start_perf = time.perf_counter()
        g._tracelet_start_dt = datetime.now(timezone.utc)

    def _after_request(self, response):
        try:
            elapsed = time.perf_counter() - g._tracelet_start_perf

            #  --- Path Normalization ---
            if request.url_rule:
                path = request.url_rule.rule
            else:
                path = request.path # Fallback for 404s where no route matched

            data = {
                "path": path,
                "method": request.method,
                "start_dt": g._tracelet_start_dt,
                "end_dt": datetime.now(timezone.utc),
                "elapsed": elapsed,
                "response_status": response.status_code,
                "framework": self.framework,
            }

            # Offload capture work to background thread to keep request path lightweight
            self.engine.worker.queue_task(self.engine.capture, data)

        except Exception as e:
            logger.error("Unexpected error in Flask Middleware: %s", e, exc_info=True)

        return response