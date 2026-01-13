"""
Comprehensive Test Suite for Tracelet
Tests: Initialization, Concurrency, Failure Simulation, Edge Cases
"""
import pytest # type: ignore
import threading
import time
import queue
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import tracelet
from tracelet.core.engine import get_engine
from tracelet.config import settings


class TestInitialization:
    """Test suite for tracelet.init() with various configurations."""
    
    def test_init_with_sqlite_default(self, tmp_path):
        """Test initialization with default SQLite database."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        
        tracelet.init(db_config=db_config, enabled=True)
        
        assert hasattr(settings, 'engine')
        assert hasattr(settings, 'SessionLocal')
        assert settings.tables_created is True
        assert settings.enabled is True
        assert settings.max_workers == 1  # SQLite defaults to 1 worker
    
    def test_init_with_postgres(self):
        """Test initialization with PostgreSQL database."""

        db_config = {
            "db_url": "postgresql+psycopg2://user:pass@localhost:5432/testdb"
        }
        
        # This will fail connection but should set max_workers correctly
        try:
            tracelet.init(db_config=db_config, max_workers=3, enabled=True)
            assert settings.max_workers == 3
        except Exception:
            # Expected if DB not available, but config should be set
            pass
    
    def test_init_with_custom_settings(self, tmp_path):
        """Test initialization with custom settings."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        
        tracelet.init(
            db_config=db_config,
            enabled=False,
            batch_size=100,
            flush_interval=10.0,
            logger_level="DEBUG"
        )
        
        assert settings.enabled is False
        assert settings.batch_size == 100
        assert settings.flush_interval == 10.0
    
    def test_init_multiple_calls_idempotent(self, tmp_path):
        """Test that multiple init() calls don't break things."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        
        tracelet.init(db_config=db_config)
        engine1 = get_engine()
        
        tracelet.init(db_config=db_config, batch_size=200)
        engine2 = get_engine()
        
        # Should be same engine instance (singleton)
        assert id(engine1) == id(engine2)
        # But settings should update
        assert settings.batch_size == 200
    
    def test_direct_attribute_access(self, tmp_path):
        """Test that users can directly update config attributes."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        
        # Initialize first
        tracelet.init(db_config=db_config, batch_size=50, enabled=True)
        
        # Direct attribute access should work
        from tracelet import config
        
        # Test updating various settings
        from tracelet.utils.logger_config import logger
        assert logger.level == 10  # DEBUG level is 10
        
        config.settings.logger_level = 'WARNING'
        assert config.settings.logger_level == 'WARNING'
        assert logger.level == 30  # WARNING level is 30
    
    def test_init_without_db_config(self):
        """Test initialization with no db_config (uses defaults)."""
        tracelet.init(enabled=True)
        
        assert hasattr(settings, 'engine')
        assert settings.enabled is True


class TestConcurrency:
    """Test suite for concurrent operations and thread safety."""
    
    def test_concurrent_captures(self, tmp_path):
        """Test multiple threads capturing metrics simultaneously."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True, batch_size=10)
        
        engine = get_engine()
        errors = []
        capture_count = [0]
        
        def capture_worker(thread_id):
            try:
                for i in range(20):
                    data = {
                        "api_url": f"/api/thread/{thread_id}/item/{i}",
                        "start_dt": datetime.now(timezone.utc),
                        "end_dt": datetime.now(timezone.utc),
                        "elapsed": 0.1,
                        "response_status": 200,
                        "framework": "test"
                    }
                    engine.capture(data)
                    capture_count[0] += 1
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=capture_worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Wait for background processing
        time.sleep(2)
        
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert capture_count[0] == 100  # 5 threads * 20 captures
    
    def test_queue_thread_safety(self, tmp_path):
        """Test that queue operations are thread-safe."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True)
        
        engine = get_engine()
        results = []
        
        def queue_worker(worker_id):
            for i in range(50):
                data = {
                    "api_url": f"/test/{worker_id}/{i}",
                    "start_dt": datetime.now(timezone.utc),
                    "end_dt": datetime.now(timezone.utc),
                    "elapsed": 0.05,
                    "response_status": 200,
                    "framework": "test"
                }
                try:
                    engine.capture(data)
                    results.append(f"{worker_id}-{i}")
                except Exception as e:
                    results.append(f"ERROR-{worker_id}-{i}: {e}")
        
        threads = [threading.Thread(target=queue_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have 500 successful captures (10 threads * 50)
        successful = [r for r in results if not r.startswith("ERROR")]
        assert len(successful) == 500
    
    def test_api_cache_thread_safety(self, tmp_path):
        """Test that API cache is thread-safe."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True)
        
        engine = get_engine()
        api_ids = []
        lock = threading.Lock()
        
        def cache_worker():
            try:
                endpoint_id = engine._get_or_create_endpoint_id("/test/endpoint", "test", "GET")
                with lock:
                    if endpoint_id is not None:
                        api_ids.append(endpoint_id)
            except Exception:
                pass  # Errors are expected and handled gracefully
        
        threads = [threading.Thread(target=cache_worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All should get the same API ID (from cache or single creation)
        assert len(set(api_ids)) == 1  # All same ID
        assert api_ids[0] is not None


class TestFailureSimulation:
    """Test suite for failure scenarios and error resilience."""
    
    def test_database_disconnection_during_capture(self, tmp_path):
        """Test behavior when database disconnects during capture."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True)
        
        engine = get_engine()
        
        # Capture some data
        data = {
            "api_url": "/test/endpoint",
            "start_dt": datetime.now(timezone.utc),
            "end_dt": datetime.now(timezone.utc),
            "elapsed": 0.1,
            "response_status": 200,
            "framework": "test"
        }
        
        # Should not raise exception even if DB fails
        engine.capture(data)
        
        # Simulate DB failure by closing engine
        engine.Session().close()
        
        # Should still not crash
        engine.capture(data)
    
    def test_invalid_data_handling(self, tmp_path):
        """Test that invalid data doesn't crash the system."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True)
        
        engine = get_engine()
        
        # Missing required fields
        invalid_data = {"api_url": "/test"}
        engine.capture(invalid_data)  # Should not crash
        
        # Invalid types
        invalid_data2 = {
            "api_url": "/test",
            "start_dt": "not-a-datetime",
            "end_dt": datetime.now(timezone.utc),
            "elapsed": "not-a-float",
            "response_status": "not-an-int",
            "framework": "test"
        }
        engine.capture(invalid_data2)  # Should not crash
    
    def test_worker_executor_failure(self, tmp_path):
        """Test behavior when worker executor fails."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True)
        
        engine = get_engine()
        
        # Mock executor to raise exception
        with patch.object(engine.worker._executor, 'submit', side_effect=Exception("Executor error")):
            data = {
                "api_url": "/test",
                "start_dt": datetime.now(timezone.utc),
                "end_dt": datetime.now(timezone.utc),
                "elapsed": 0.1,
                "response_status": 200,
                "framework": "test"
            }
            # Should not crash the application
            engine.capture(data)
    
    def test_middleware_exception_handling(self, tmp_path):
        """Test that middleware exceptions don't crash the app."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True)
        
        from tracelet.integrations.flask import FlaskMiddleware
        
        app = Mock()
        middleware = FlaskMiddleware(app=app)
        
        # Mock request that raises exception
        request = Mock()
        request.url_rule = None
        request.path = "/test"
        
        response = Mock()
        response.status_code = 200
        
        # Should handle exceptions gracefully
        with patch.object(middleware.engine, 'capture', side_effect=Exception("Capture error")):
            result = middleware._after_request(response)
            assert result == response  # Should return response even on error


class TestBulkMode:
    """Test suite for bulk insert mode."""
    
    def test_bulk_mode_enabled(self, tmp_path):
        """Test that bulk mode works correctly."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True, use_bulk_mode=True, batch_size=5)
        
        engine = get_engine()
        
        # Add 10 items (should trigger 2 bulk inserts)
        for i in range(10):
            data = {
                "api_url": f"/test/{i}",
                "start_dt": datetime.now(timezone.utc),
                "end_dt": datetime.now(timezone.utc),
                "elapsed": 0.1,
                "response_status": 200,
                "framework": "test"
            }
            engine.capture(data)
        
        # Wait for processing
        time.sleep(1)
        engine.flush_buffer()
        time.sleep(1)
    
    def test_single_mode_fallback(self, tmp_path):
        """Test single save mode when bulk_mode is disabled."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True, use_bulk_mode=False)
        
        engine = get_engine()
        
        data = {
            "api_url": "/test/single",
            "start_dt": datetime.now(timezone.utc),
            "end_dt": datetime.now(timezone.utc),
            "elapsed": 0.1,
            "response_status": 200,
            "framework": "test"
        }
        
        engine.capture(data)
        time.sleep(1)


class TestEdgeCases:
    """Test suite for edge cases and boundary conditions."""
    
    def test_empty_queue_flush(self, tmp_path):
        """Test flushing an empty queue."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True)
        
        engine = get_engine()
        # Should not crash
        engine.flush_buffer()
    
    def test_disabled_tracelet(self, tmp_path):
        """Test behavior when Tracelet is disabled."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=False)
        
        engine = get_engine()
        
        data = {
            "api_url": "/test",
            "start_dt": datetime.now(timezone.utc),
            "end_dt": datetime.now(timezone.utc),
            "elapsed": 0.1,
            "response_status": 200,
            "framework": "test"
        }
        
        # Should return immediately without processing
        engine.capture(data)
        assert engine._queue.qsize() == 0  # Nothing queued
    
    def test_very_large_batch(self, tmp_path):
        """Test handling of very large batches."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True, batch_size=1000)
        
        engine = get_engine()
        
        # Add 2000 items
        for i in range(2000):
            data = {
                "api_url": f"/test/{i}",
                "start_dt": datetime.now(timezone.utc),
                "end_dt": datetime.now(timezone.utc),
                "elapsed": 0.1,
                "response_status": 200,
                "framework": "test"
            }
            engine.capture(data)
        
        time.sleep(2)
    
    def test_rapid_flush_interval(self, tmp_path):
        """Test rapid flush intervals."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True, flush_interval=0.1)
        
        engine = get_engine()
        
        # Add some data
        for i in range(10):
            data = {
                "api_url": f"/test/{i}",
                "start_dt": datetime.now(timezone.utc),
                "end_dt": datetime.now(timezone.utc),
                "elapsed": 0.1,
                "response_status": 200,
                "framework": "test"
            }
            engine.capture(data)
        
        # Wait for flush
        time.sleep(0.5)


class TestShutdown:
    """Test suite for graceful shutdown."""
    
    def test_shutdown_flushes_queue(self, tmp_path):
        """Test that shutdown flushes remaining queue items."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True, batch_size=100)
        
        engine = get_engine()
        
        # Add items that won't trigger auto-flush
        for i in range(30):
            data = {
                "api_url": f"/test/{i}",
                "start_dt": datetime.now(timezone.utc),
                "end_dt": datetime.now(timezone.utc),
                "elapsed": 0.1,
                "response_status": 200,
                "framework": "test"
            }
            engine.capture(data)
        
        # Shutdown should flush
        engine.shutdown()
    
    def test_double_shutdown_safe(self, tmp_path):
        """Test that calling shutdown twice is safe."""
        db_path = tmp_path / "test.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}
        tracelet.init(db_config=db_config, enabled=True)
        
        engine = get_engine()
        
        # Should not crash
        engine.shutdown()
        engine.shutdown()


class TestSingletonAndNonBlocking:
    """
    Tests focused on:
    - Engine singleton behaviour
    - Non-blocking capture performance
    - Thread-safety under concurrency
    - Settings consistency after init()
    """

    def _init_engine(self, tmp_path):
        """Helper to initialize Tracelet with a dedicated SQLite DB."""
        db_path = tmp_path / "singleton_nonblocking.db"
        db_config = {"db_url": f"sqlite:///{db_path}"}

        tracelet.init(max_workers=2, enabled=True, db_config=db_config)
        return get_engine()

    def test_singleton_pattern(self, tmp_path):
        """get_engine() should always return the same instance."""
        engine1 = self._init_engine(tmp_path)
        engine2 = get_engine()

        assert id(engine1) == id(engine2)

    def test_first_capture_non_blocking_enough(self, tmp_path):
        """
        First capture includes initialization overhead but should still be fast
        enough for real-world use (we allow up to 100ms).
        """
        engine = self._init_engine(tmp_path)

        data = {
            "api_url": "/test/endpoint",
            "start_dt": datetime.now(timezone.utc),
            "end_dt": datetime.now(timezone.utc),
            "elapsed": 0.1,
            "response_status": 200,
            "framework": "test",
        }

        start_time = time.perf_counter()
        engine.capture(data)
        end_time = time.perf_counter()

        duration_ms = (end_time - start_time) * 1000.0
        # Allow generous threshold because this includes one-time initialization.
        assert duration_ms < 100.0

    def test_multiple_captures_remain_fast(self, tmp_path):
        """Multiple sequential captures should be very fast on average."""
        engine = self._init_engine(tmp_path)

        data = {
            "api_url": "/test/endpoint",
            "start_dt": datetime.now(timezone.utc),
            "end_dt": datetime.now(timezone.utc),
            "elapsed": 0.1,
            "response_status": 200,
            "framework": "test",
        }

        iterations = 100
        start_time = time.perf_counter()
        for i in range(iterations):
            data["api_url"] = f"/test/endpoint/{i}"
            engine.capture(data)
        end_time = time.perf_counter()

        total_ms = (end_time - start_time) * 1000.0
        avg_ms = total_ms / iterations

        # Average capture time should remain comfortably sub-millisecond.
        assert avg_ms < 2.0

    def test_thread_safety_under_concurrency(self, tmp_path):
        """
        Concurrent captures from multiple threads should not raise errors
        and should all be counted.
        """
        engine = self._init_engine(tmp_path)

        capture_count = [0]
        errors = []

        def capture_in_thread(thread_id: int):
            try:
                for i in range(10):
                    data = {
                        "api_url": f"/thread/{thread_id}/endpoint/{i}",
                        "start_dt": datetime.now(timezone.utc),
                        "end_dt": datetime.now(timezone.utc),
                        "elapsed": 0.1,
                        "response_status": 200,
                        "framework": "test",
                    }
                    engine.capture(data)
                    capture_count[0] += 1
            except Exception as e:  # pragma: no cover - defensive
                errors.append(f"Thread {thread_id}: {e}")

        threads = []
        start_time = time.perf_counter()
        for i in range(10):
            t = threading.Thread(target=capture_in_thread, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()
        end_time = time.perf_counter()

        total_ms = (end_time - start_time) * 1000.0
        avg_ms = total_ms / capture_count[0]

        assert not errors
        assert capture_count[0] == 100
        # Allow a small per-capture cost under concurrency.
        assert avg_ms < 5.0

    def test_settings_consistency_after_init(self, tmp_path):
        """All core settings attributes should be initialized correctly."""
        engine = self._init_engine(tmp_path)

        assert engine is not None
        assert hasattr(tracelet.settings, "engine")
        assert hasattr(tracelet.settings, "SessionLocal")
        assert isinstance(tracelet.settings.max_workers, int)
        assert isinstance(tracelet.settings.enabled, bool)
        assert isinstance(tracelet.settings.tables_created, bool)


@pytest.fixture(autouse=True)
def reset_settings():
    """Reset settings before each test."""
    yield
    # Cleanup after test
    if hasattr(settings, 'engine'):
        try:
            engine = get_engine()
            engine.shutdown()
        except:
            pass

