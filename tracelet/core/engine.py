from tracelet.db.models import APIs, Metrics, APIStatus
from sqlalchemy import select
from tracelet.utils.helper import format_as_seconds, clean_url_path
from tracelet.config import settings
from .worker import AsyncWorker
from tracelet.logger_config import logger
import http
import queue
import threading
import atexit
import uuid

_shared_engine_instance = None

class _Engine:
    def __init__(self, db_session_factory=None):
        # Lazy access to avoid evaluating settings.SessionLocal at class definition time
        if db_session_factory is None:
            if not hasattr(settings, 'SessionLocal'):
                raise RuntimeError(
                    "Tracelet not initialized. Please call tracelet.init() before creating Engine."
                )
            db_session_factory = settings.SessionLocal
        self.Session = db_session_factory
        self.worker = AsyncWorker()
        
        # Thread-safe queue for buffering metrics
        self._queue = queue.Queue()
        
        # API cache (Key: (api_url_path, framework) -> Value: api_id)
        self._api_cache = {}
        self._cache_lock = threading.Lock()
        
        # Start heartbeat timer for periodic flush
        self._schedule_flush()
        
        # Register shutdown to flush queue (independent of worker shutdown)
        # Note: atexit calls in reverse order, so Engine.shutdown runs before Worker.stop
        atexit.register(self.shutdown)
    
    def _schedule_flush(self):
        """Schedule the next heartbeat flush."""
        if not settings.enabled:
            return
        interval = getattr(settings, 'flush_interval', 5.0)
        self._timer = threading.Timer(interval, self._heartbeat_flush)
        self._timer.daemon = True
        self._timer.start()
    
    def _heartbeat_flush(self):
        """Heartbeat callback to flush queue periodically."""
        self.flush_buffer()
        self._schedule_flush()
    
    def _get_or_create_api_id(self, api_url_path, framework):
        """Get or create API ID with thread-safe caching (Single Save)."""
        cache_key = (api_url_path, framework)

        # 1. First check WITHOUT a lock (Lightning fast)
        if cache_key in self._api_cache:
            return self._api_cache[cache_key]
        
        # 2. If it's a miss, grab the lock to do the DB work safely
        with self._cache_lock:
            # Re-check inside the lock in case another thread just created it
            if cache_key in self._api_cache:
                return self._api_cache[cache_key]           
            # Cache miss - hit the database (single save)
            session = self.Session()
            try:
                stmt = select(APIs).where(
                    APIs.api_url_path == api_url_path,
                    APIs.framework == framework
                )
                api_obj = session.scalars(stmt).one_or_none()
                
                if not api_obj:
                    api_obj = APIs(api_url_path=api_url_path, framework=framework)
                    session.add(api_obj)
                    session.commit()
                    session.refresh(api_obj)

                api_id = api_obj.api_id
                self._api_cache[cache_key] = api_id # Store in cache for future lookups
                return api_id
            
            except Exception as e:
                session.rollback()
                logger.error("Tracelet API lookup error: %s", e, exc_info=True)
                return None
            finally:
                session.close()

    def capture(self, data):
        """The main entry point for all frameworks - Non-blocking."""
        if not settings.enabled:
            return

        try:
            # Determine success/fail
            status_code = data["response_status"]
            status = APIStatus.SUCCESS if 200 <= status_code < 300 else APIStatus.FAILED
            
            try:
                detail = http.HTTPStatus(status_code).phrase
            except ValueError:
                detail = "Unknown Status"

            elapsed_secs = float(format_as_seconds(data["elapsed"]))
            elapsed_ms = elapsed_secs*1000

            api_url_path = clean_url_path(data["api_url"])
            framework = data["framework"]
            
            # Get API ID immediately (single save with cache) - ensures FK is ready
            api_id = self._get_or_create_api_id(api_url_path, framework)
            if api_id is None:
                return  # Skip if API lookup failed
            
            # Prepare metric data (ready for bulk insert)
            prepared = {
                "unique_id": str(uuid.uuid4()),
                "api_url_id": api_id,
                "requested_time": data["start_dt"],
                "responded_time": data["end_dt"],
                "time_taken_secs": elapsed_secs,
                "time_taken_ms": elapsed_ms,
                "response_json": {"status_code": status_code, "detail": detail},
                "response_status": status
            }
            
            # Put in queue (lightning fast, non-blocking)
            self._queue.put(prepared)
            
            # Trigger flush if batch size reached
            if self._queue.qsize() >= getattr(settings, 'batch_size', 50):
                self.flush_buffer()
        except Exception as e:
            logger.error("Exception occurred during metrics capture: %s", e, exc_info=True)
    
    def flush_buffer(self):
        """Extract items from queue and send to worker for batch processing.
        
        Thread-safe implementation that handles race conditions where items
        may be added to the queue while flushing.
        """
        batch = []
        # Use get_nowait with exception handling instead of empty() check
        # This avoids race conditions where queue becomes non-empty between
        # empty() check and get_nowait() call
        while True:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        
        if batch:
            if settings.use_bulk_mode:
                # Bulk save (high performance)
                self.worker.queue_task(self._bulk_save_metrics, batch)
            else:
                # Single save mode (backward compatibility)
                for item in batch:
                    self.worker.queue_task(self._single_save_metric, item)
    
    def _bulk_save_metrics(self, data_list):
        """Bulk insert metrics using bulk_insert_mappings (high performance)."""
        session = self.Session()
        try:
            session.bulk_insert_mappings(Metrics, data_list)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Tracelet Bulk Save Error: %s", e, exc_info=True)
        finally:
            session.close()
    
    def _single_save_metric(self, data):
        """Single save for backward compatibility when bulk_mode is disabled."""
        session = self.Session()
        try:
            session.add(Metrics(**data))
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Tracelet Single Save Error: %s", e, exc_info=True)
        finally:
            session.close()
    
    def shutdown(self):
            """The Master Shutdown Sequence."""
            # Use a flag to prevent double-shutdown if called manually
            if getattr(self, '_in_shutdown', False):
                logger.debug("Shutdown already in progress; skipping duplicate call.")
                return
            self._in_shutdown = True

            try:
                if hasattr(self, '_timer'): # 1. Stop the heartbeat timer immediately
                    self._timer.cancel()

                # 2. Check if the worker's executor is still accepting tasks
                # This is the key to stopping that 'RuntimeError'
                if hasattr(self, 'worker') and self.worker._executor:
                    if not self.worker._executor._shutdown:  # Check if executor is NOT shut down before flushing
                        self.flush_buffer()
                    
                    self.worker.stop() # 3. Gracefully stop the worker
            except Exception as e:
                logger.error("Error during shutdown: %s", e, exc_info=True)
            finally:
                logger.info("Tracelet: Shutdown complete.")

def get_engine():
    """
    This is the ONLY way to get the engine. 
    It ensures we never create more than one.
    """
    global _shared_engine_instance
    if _shared_engine_instance is None:
        _shared_engine_instance = _Engine()
    return _shared_engine_instance