from tracelet.db.models import Endpoints, Metrics, Buckets, EndpointStatus
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from tracelet.utils.helper import clean_url_path, get_latency_bucket
from tracelet.config import settings
from .worker import AsyncWorker
from tracelet.utils.logger_config import logger
from collections import defaultdict
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
        
        self._queue = queue.Queue()
        
        # endpoint cache (Key: (path, framework) -> Value: endpoint_id)
        self._endpoint_cache = {}
        self._cache_lock = threading.Lock()
        
        self._schedule_flush()
        atexit.register(self.shutdown)
    
    def _schedule_flush(self):
        """Schedule the next heartbeat flush."""
        if not settings.enabled:
            return
        interval = getattr(settings, 'flush_interval', 5.0)
        logger.debug(f"Schedule for flush started. Flush starts in {interval}s")
        self._timer = threading.Timer(interval, self._heartbeat_flush)
        self._timer.daemon = True
        self._timer.start()
    
    def _heartbeat_flush(self):
        """Heartbeat callback to flush queue periodically."""
        self.flush_buffer()
        self._schedule_flush()
    
    def _get_or_create_endpoint_id(self, path, framework):
        """Get or create endpoint ID with thread-safe caching (Single Save)."""
        cache_key = (path, framework)

        if cache_key in self._endpoint_cache:
            return self._endpoint_cache[cache_key]
        
        with self._cache_lock:
            if cache_key in self._endpoint_cache:
                return self._endpoint_cache[cache_key]           
            session = self.Session()
            try:
                stmt = select(Endpoints).where(
                    Endpoints.path == path,
                    Endpoints.framework == framework
                )
                endpoint_obj = session.scalars(stmt).one_or_none()
                
                if not endpoint_obj:
                    endpoint_obj = Endpoints(path=path, method="GET", framework=framework) # Set method : GET as dummy until implemented emthod capture
                    session.add(endpoint_obj)
                    session.commit()
                    session.refresh(endpoint_obj)

                endpoint_id = endpoint_obj.endpoint_id
                self._endpoint_cache[cache_key] = endpoint_id # Store in cache for future lookups
                return endpoint_id
            
            except Exception as e:
                session.rollback()
                logger.error("Tracelet Endpoint lookup error: %s", e, exc_info=True)
                return None
            finally:
                session.close()

    def capture(self, data):
        """The main entry point for all frameworks - Non-blocking."""
        if not settings.enabled:
            return

        try:
            status_code = data["response_status"]
            status = EndpointStatus.SUCCESS if 200 <= status_code < 300 else EndpointStatus.FAILED
            
            try:
                detail = http.HTTPStatus(status_code).phrase
            except ValueError:
                detail = "Unknown Status"

            elapsed_ms = data["elapsed"]*1000
            bucket_le = get_latency_bucket(elapsed_ms)

            path = clean_url_path(data["path"])
            framework = data["framework"]
            
            endpoint_id = self._get_or_create_endpoint_id(path, framework)
            if endpoint_id is None:
                return  # Skip if endpoint lookup failed
            
            metrics_data = {
                "unique_id": str(uuid.uuid4()),
                "endpoint_id": endpoint_id,
                "request_time": data["start_dt"],
                "response_time": data["end_dt"],
                "latency_ms": elapsed_ms,
                "response_json": {"status_code": status_code, "detail": detail},
                "response_status": status
            }

            bucket_data = {"le" : bucket_le, "endpoint_id" : endpoint_id}
            
            # Put in queue (lightning fast, non-blocking)
            self._queue.put((metrics_data, bucket_data))
            
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
        metric_batch = []
        bucket_batch = []

        while True:
            try:
                batch_data = self._queue.get_nowait()
                metric_batch.append(batch_data[0])
                bucket_batch.append(batch_data[1])
            except queue.Empty:
                break
                
        logger.debug(f"Initiating data flush. Metrics data: {len(metric_batch)}, Bucket Data: {len(bucket_batch)}")
        if metric_batch:
            self.worker.queue_task(self._bulk_save_metrics, metric_batch, bucket_batch)

    def _prepare_bucket(self, bucket_batch):
        # Aggregate buckets
        logger.debug("Aggregating Bucket for Bulk Insertion")
        bucket_counters = defaultdict(int)
        for bucket in bucket_batch:
            key = (bucket['endpoint_id'], bucket['le'])
            bucket_counters[key] += 1
        
        bucket_data = [
            {'endpoint_id': eid, 'le': le, 'count': cnt}
            for (eid, le), cnt in bucket_counters.items()
        ]
        
        return bucket_data
    
    def _bulk_save_metrics(self, metrics_data, bucket_batch):
        """Bulk insert metrics using bulk_insert_mappings (high performance)."""
        session = self.Session()
        import time # To test performance
        start = time.perf_counter() # To test performance
        try:
            bucket_data = self._prepare_bucket(bucket_batch)
            agg_time = (time.perf_counter() - start) * 1000 # To test performance
            with session.begin():
                logger.debug("Initiating transaction for bulk Metrics and Buckets insertion")
                session.bulk_insert_mappings(Metrics, metrics_data)
                if bucket_data:
                    insert = pg_insert if settings.db_type == 'postgres' else sqlite_insert
                    stmt = insert(Buckets).values(bucket_data)
                    stmt = stmt.on_conflict_do_update(
                        constraint='_endpoint_bucket_uc',
                        set_={'count': Buckets.count + stmt.excluded.count}
                    )
                    session.execute(stmt)
                session.commit()
            total_time = (time.perf_counter() - start) * 1000 # To test performance
            logger.debug(f"Bulk save: {len(metrics_data)} records, agg={agg_time:.2f}ms, total={total_time:.2f}ms") # To test performance
            logger.debug("Completed bulk insertion transaction")
        except Exception as e:
            session.rollback()
            logger.error("Tracelet Bulk Save Error: %s", e, exc_info=True)
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