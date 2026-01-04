from tracelet.db.config import SessionLocal
from tracelet.db.models import APIs, Metrics, APIStatus
from sqlalchemy import select
from tracelet.utils.helper import format_as_seconds
from tracelet.config import settings
from .worker import AsyncWorker
import http

_shared_engine_instance = None

class Engine:
    def __init__(self, db_session_factory=SessionLocal):
        self.Session = db_session_factory
        self.worker = AsyncWorker()

    def capture(self, data):
        """The main entry point for all frameworks"""
        # Determine success/fail
        status_code = data["response_status"]
        status = APIStatus.SUCCESS if 200 <= status_code < 300 else APIStatus.FAILED
        
        try:
            detail = http.HTTPStatus(status_code).phrase
        except ValueError:
            detail = "Unknown Status"

        unique_id = f"{data['start_dt'].timestamp()}-{data['api_url']}-{data['end_dt'].timestamp()}"
        elapsed_secs = float(format_as_seconds(data["elapsed"]))
        elapsed_ms = elapsed_secs*1000

        prepared = {
            "api_url": self.clean_path(data["api_url"]),
            "unique_id": unique_id,
            "requested_time": data["start_dt"],
            "responded_time": data["end_dt"],
            "time_taken_secs": elapsed_secs,
            "time_taken_ms": elapsed_ms,
            "response_json": {"status_code": status_code, "detail": detail},
            "response_status": status,
            "framework": data["framework"]
        }
        
        self._save_to_db(prepared)

    def start_concurrent_store(self, data):
        if not settings.enabled:
            return
        self.worker.queue_task(self.capture, data)

    def clean_path(self, path):
        path = path.strip()
        if not path.startswith("/"):
            path = "/" + path
        if path.endswith("/") and len(path) > 1:
            path = path.rstrip("/")
        return path

    def _save_to_db(self, prepared):
        db = self.Session()
        try:
            # Your existing logic to find/create API and save Metrics
            stmt = select(APIs).where(
                APIs.api_url_path == prepared["api_url"],
                APIs.framework == prepared["framework"]
            )
            api_obj = db.scalars(stmt).one_or_none()
            
            if not api_obj:
                api_obj = APIs(api_url_path=prepared["api_url"], framework=prepared["framework"])
                db.add(api_obj)
                db.flush()

            prepared["api_url_id"] = api_obj.api_id
            prepared.pop("api_url") # Clean up for Metrics model
            prepared.pop("framework")
            
            db.add(Metrics(**prepared))
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Tracelet encountered an Error: {e}")
        finally:
            db.close()

def get_engine():
    """
    This is the ONLY way to get the engine. 
    It ensures we never create more than one.
    """
    global _shared_engine_instance
    if _shared_engine_instance is None:
        _shared_engine_instance = Engine()
    return _shared_engine_instance