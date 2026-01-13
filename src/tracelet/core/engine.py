from tracelet.db.models import Endpoints, Metrics, Buckets, EndpointStatus
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from tracelet.utils.helper import clean_url_path, get_latency_bucket
from tracelet.config import settings
from .worker import AsyncWorker
from tracelet.utils.logger_config import logger
from datetime import datetime, timezone
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
            if not hasattr(settings, "SessionLocal"):
                raise RuntimeError(
                    "Tracelet not initialized. Please call tracelet.init() before creating Engine."
                )
            db_session_factory = settings.SessionLocal
        self.Session = db_session_factory
        self.worker = AsyncWorker()
        self._bootstrapped = False
        self.cumulative_counter = defaultdict(int)

        self._queue = queue.Queue()

        # endpoint cache (Key: (path, method, framework) -> Value: endpoint_id)
        self._endpoint_cache = {}
        self._cache_lock = threading.Lock()

        self._schedule_flush()
        atexit.register(self.shutdown)

    def _schedule_flush(self):
        """Schedule the next heartbeat flush."""
        if not settings.enabled:
            return
        interval = getattr(settings, "flush_interval", 5.0)
        logger.debug(f"Schedule for flush started. Flush starts in {interval}s")
        self._timer = threading.Timer(interval, self._heartbeat_flush)
        self._timer.daemon = True
        self._timer.start()

    def _heartbeat_flush(self):
        """Heartbeat callback to flush queue periodically."""
        self.flush_buffer()
        self._schedule_flush()

    def _get_or_create_endpoint_id(self, path, framework, method):
        """Get or create endpoint ID with thread-safe caching (Single Save)."""
        cache_key = (path, method, framework)

        if cache_key in self._endpoint_cache:
            return self._endpoint_cache[cache_key]

        with self._cache_lock:
            if cache_key in self._endpoint_cache:
                return self._endpoint_cache[cache_key]
            session = self.Session()
            try:
                stmt = select(Endpoints).where(
                    Endpoints.path == path,
                    Endpoints.method == method,
                    Endpoints.framework == framework,
                )
                endpoint_obj = session.scalars(stmt).one_or_none()

                if not endpoint_obj:
                    endpoint_obj = Endpoints(
                        path=path, method=method, framework=framework
                    )
                    session.add(endpoint_obj)
                    session.commit()
                    session.refresh(endpoint_obj)

                endpoint_id = endpoint_obj.endpoint_id
                self._endpoint_cache[cache_key] = (
                    endpoint_id  # Store in cache for future lookups
                )
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
            status = (
                EndpointStatus.SUCCESS
                if 200 <= status_code < 300
                else EndpointStatus.FAILED
            )

            try:
                detail = http.HTTPStatus(status_code).phrase
            except ValueError:
                detail = "Unknown Status"

            elapsed_ms = data["elapsed"] * 1000
            bucket_le = get_latency_bucket(elapsed_ms)

            path = clean_url_path(data["path"])
            framework = data["framework"]
            method = data["method"]

            endpoint_id = self._get_or_create_endpoint_id(
                path, framework, method=method
            )
            if endpoint_id is None:
                return  # Skip if endpoint lookup failed

            metrics_data = {
                "unique_id": str(uuid.uuid4()),
                "endpoint_id": endpoint_id,
                "request_time": data["start_dt"],
                "response_time": data["end_dt"],
                "latency_ms": elapsed_ms,
                "response_json": {"status_code": status_code, "detail": detail},
                "response_status": status,
            }

            bucket_data = {"le": bucket_le, "endpoint_id": endpoint_id}

            # Put in queue (lightning fast, non-blocking)
            self._queue.put((metrics_data, bucket_data))

            # Trigger flush if batch size reached
            if self._queue.qsize() >= getattr(settings, "batch_size", 50):
                self.flush_buffer()
        except Exception as e:
            logger.error(
                "Exception occurred during metrics capture: %s", e, exc_info=True
            )

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

        logger.debug(
            f"Initiating data flush. Metrics data: {len(metric_batch)}, Bucket Data: {len(bucket_batch)}"
        )
        if metric_batch:
            self.worker.queue_task(self._bulk_save_metrics, metric_batch, bucket_batch)

    def _load_last_counts(self, session):
        """Populate bucket cumulative counts from DB and ensure all thresholds are initialized.

        After loading existing bucket data, initializes all thresholds to 0 for endpoints
        that exist but have incomplete bucket data. This ensures complete snapshots.
        """
        # Use the flag to avoid re-checking an empty DB
        if getattr(self, "_bootstrapped", False):
            return

        logger.info("Bootstrapping cumulative counters from DB...")
        try:
            latest_timestamp = session.query(func.max(Buckets.captured_at)).scalar()

            if latest_timestamp:
                # Load existing bucket counts from latest snapshot
                last_entries = (
                    session.query(Buckets.endpoint_id, Buckets.le, Buckets.count)
                    .filter(Buckets.captured_at == latest_timestamp)
                    .all()
                )
                for eid, le, count in last_entries:
                    self.cumulative_counter[(eid, le)] = count

                # Get all endpoint_ids that have bucket data
                endpoint_ids_with_buckets = {eid for eid, _, _ in last_entries}

                # Ensure ALL thresholds exist for each endpoint (initialize missing to 0)
                for eid in endpoint_ids_with_buckets:
                    for threshold in settings.BUCKET_THRESHOLDS:
                        if (eid, threshold) not in self.cumulative_counter:
                            self.cumulative_counter[(eid, threshold)] = 0
                            logger.debug(
                                f"Initialized missing threshold {threshold}ms for endpoint {eid} to 0"
                            )
            else:
                # No existing data - check if endpoints exist and initialize all thresholds
                existing_endpoints = session.query(Endpoints.endpoint_id).all()
                for (eid,) in existing_endpoints:
                    for threshold in settings.BUCKET_THRESHOLDS:
                        if (eid, threshold) not in self.cumulative_counter:
                            self.cumulative_counter[(eid, threshold)] = 0

            self._bootstrapped = True  # Success flag
            logger.info("Bucket cumulative counters bootstrapped successfully")
        except Exception as e:
            logger.error(
                "Error occurred during bucket cumulative count load: %s",
                e,
                exc_info=True,
            )

    def _prepare_bucket(self, bucket_batch):
        """Update the running totals in memory and return the new snapshot.

        Ensures ALL bucket thresholds are included in every snapshot for complete histogram representation.
        Missing thresholds are initialized to 0 (or existing cumulative count if already present).
        """
        # 1. Update cumulative counters for requests in this batch
        endpoint_ids_in_batch = set()
        for item in bucket_batch:
            eid = item["endpoint_id"]
            assigned_le = item["le"]
            endpoint_ids_in_batch.add(eid)

            for threshold in settings.BUCKET_THRESHOLDS:
                if assigned_le <= threshold:
                    self.cumulative_counter[(eid, threshold)] += 1

        # 2. Ensure ALL thresholds exist for each endpoint in this batch
        # This guarantees complete snapshots even if some thresholds never received requests
        for eid in endpoint_ids_in_batch:
            for threshold in settings.BUCKET_THRESHOLDS:
                # Initialize to 0 if not present (ensures all thresholds in snapshot)
                if (eid, threshold) not in self.cumulative_counter:
                    self.cumulative_counter[(eid, threshold)] = 0

        now = datetime.now(timezone.utc)

        # 3. Return snapshot with ALL thresholds for endpoints in this batch
        # Note: This returns all thresholds for endpoints in batch, not all endpoints ever seen
        # This is correct because we only need complete snapshots for endpoints with new data
        snapshot_data = []
        for eid in endpoint_ids_in_batch:
            for threshold in settings.BUCKET_THRESHOLDS:
                count = self.cumulative_counter.get((eid, threshold), 0)
                snapshot_data.append(
                    {
                        "endpoint_id": eid,
                        "le": threshold,
                        "count": count,
                        "captured_at": now,
                    }
                )

        return snapshot_data

    def _bulk_save_metrics(self, metrics_data, bucket_batch):
        """Bulk insert metrics using bulk_insert_mappings (high performance)."""
        session = self.Session()
        try:
            bucket_data = self._prepare_bucket(bucket_batch)
            with session.begin():
                logger.debug(
                    "Initiating transaction for bulk Metrics and Buckets insertion"
                )
                session.bulk_insert_mappings(Metrics, metrics_data)
                if bucket_data:
                    conflict_cols = [
                        Buckets.endpoint_id,
                        Buckets.le,
                        Buckets.captured_at,
                    ]
                    insert = (
                        pg_insert if settings.db_type == "postgres" else sqlite_insert
                    )
                    stmt = insert(Buckets).values(bucket_data)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=conflict_cols,
                        set_={"count": stmt.excluded.count},
                    )
                    session.execute(stmt)
                session.commit()
            logger.debug("Completed bulk insertion transaction")
        except Exception as e:
            session.rollback()
            logger.error("Tracelet Bulk Save Error: %s", e, exc_info=True)
        finally:
            session.close()

    def shutdown(self):
        """The Master Shutdown Sequence."""
        # Use a flag to prevent double-shutdown if called manually
        if getattr(self, "_in_shutdown", False):
            logger.debug("Shutdown already in progress; skipping duplicate call.")
            return
        self._in_shutdown = True

        try:
            if hasattr(self, "_timer"):  # 1. Stop the heartbeat timer immediately
                self._timer.cancel()

            if hasattr(self, "worker") and self.worker._executor:
                if (
                    not self.worker._executor._shutdown
                ):  # Check if executor is NOT shut down before flushing
                    self.flush_buffer()

                self.worker.stop()  # 3. Gracefully stop the worker
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
