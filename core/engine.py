from db.config import SessionLocal
from db.models import APIs, Metrics, APIStatus
from sqlalchemy import select
from utils.helper import format_as_seconds
import http

class TraceletEngine:
    def __init__(self, db_session_factory=SessionLocal):
        self.Session = db_session_factory

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