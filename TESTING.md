# Tracelet Testing Guide

**Last Updated:** January 2025  
**Test Framework:** pytest  
**Coverage Target:** 80%+

---

## Quick Start

### Installation

```bash
pip install pytest pytest-cov
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=tracelet --cov-report=html

# Run specific test file
pytest tests/test_comprehensive.py

# Run specific test class
pytest tests/test_comprehensive.py::TestInitialization

# Run with verbose output
pytest -v
```

---

## Test Structure

### Test Files

```
tests/
├── __init__.py
├── test_comprehensive.py    # Main comprehensive test suite
├── test_django.py           # Django integration example
├── test_fastapi.py          # FastAPI integration example
├── test_flask.py            # Flask integration example
└── test_init_singleton_nonblocking.py  # Singleton & non-blocking tests
```

---

## Test Categories

### 1. Initialization Tests (`TestInitialization`)

Tests for `tracelet.init()` with various configurations.

**Tests:**
- `test_init_with_sqlite_default` - Default SQLite initialization
- `test_init_with_postgres` - PostgreSQL initialization
- `test_init_with_custom_settings` - Custom configuration
- `test_init_multiple_calls_idempotent` - Multiple init() calls
- `test_init_without_db_config` - Default configuration

**How to Run:**
```bash
pytest tests/test_comprehensive.py::TestInitialization -v
```

**Expected Results:**
- All tests should pass
- Database tables should be created
- Settings should be properly configured

---

### 2. Concurrency Tests (`TestConcurrency`)

Tests for thread safety and concurrent operations.

**Tests:**
- `test_concurrent_captures` - Multiple threads capturing simultaneously
- `test_queue_thread_safety` - Queue operations under concurrency
- `test_api_cache_thread_safety` - API cache thread safety

**How to Run:**
```bash
pytest tests/test_comprehensive.py::TestConcurrency -v
```

**Expected Results:**
- No errors in concurrent operations
- All captures should succeed
- Thread-safe behavior verified

**Performance Expectations:**
- Sequential captures: ~0.12ms average
- Concurrent captures: ~1.2ms average (10 threads)

---

### 3. Failure Simulation Tests (`TestFailureSimulation`)

Tests for error resilience and failure scenarios.

**Tests:**
- `test_database_disconnection_during_capture` - DB disconnection handling
- `test_invalid_data_handling` - Invalid data handling
- `test_worker_executor_failure` - Executor failure handling
- `test_middleware_exception_handling` - Middleware error handling

**How to Run:**
```bash
pytest tests/test_comprehensive.py::TestFailureSimulation -v
```

**Expected Results:**
- No application crashes
- Errors are logged but not propagated
- Graceful degradation

**Key Assertions:**
- Application continues to function
- Errors are caught and logged
- No data corruption

---

### 4. Bulk Mode Tests (`TestBulkMode`)

Tests for bulk insert mode functionality.

**Tests:**
- `test_bulk_mode_enabled` - Bulk mode operation
- `test_single_mode_fallback` - Single save mode fallback

**How to Run:**
```bash
pytest tests/test_comprehensive.py::TestBulkMode -v
```

**Expected Results:**
- Bulk inserts work correctly
- Single mode works as fallback
- No data loss

---

### 5. Edge Cases Tests (`TestEdgeCases`)

Tests for edge cases and boundary conditions.

**Tests:**
- `test_empty_queue_flush` - Flushing empty queue
- `test_disabled_tracelet` - Behavior when disabled
- `test_very_large_batch` - Large batch handling
- `test_rapid_flush_interval` - Rapid flush intervals

**How to Run:**
```bash
pytest tests/test_comprehensive.py::TestEdgeCases -v
```

**Expected Results:**
- No crashes on edge cases
- Proper handling of boundary conditions
- Graceful degradation

---

### 6. Shutdown Tests (`TestShutdown`)

Tests for graceful shutdown behavior.

**Tests:**
- `test_shutdown_flushes_queue` - Queue flush on shutdown
- `test_double_shutdown_safe` - Double shutdown safety

**How to Run:**
```bash
pytest tests/test_comprehensive.py::TestShutdown -v
```

**Expected Results:**
- Queue is flushed on shutdown
- No errors on double shutdown
- Resources are properly cleaned up

---

## Interpreting Test Results

### Success Criteria

✅ **All tests pass** - Code is working correctly  
✅ **No errors** - No exceptions or failures  
✅ **No warnings** - No deprecation or performance warnings  
✅ **Coverage > 70%** - Good test coverage

### Common Issues

#### Test Failures

**Issue:** `RuntimeError: Tracelet not initialized`
- **Cause:** `tracelet.init()` not called before test
- **Fix:** Add `tracelet.init()` in test setup

**Issue:** `Database is locked`
- **Cause:** Multiple threads accessing SQLite simultaneously
- **Fix:** Ensure `max_workers=1` for SQLite

**Issue:** `AttributeError: 'Settings' object has no attribute 'engine'`
- **Cause:** Settings not properly initialized
- **Fix:** Call `tracelet.init()` before accessing settings

#### Performance Warnings

**Warning:** `capture() took > 1ms`
- **Expected:** First call may take ~45ms (initialization overhead)
- **Action:** Only warn if subsequent calls exceed threshold

**Warning:** `Average capture time > 0.2ms`
- **Expected:** Should be ~0.12ms average
- **Action:** Investigate if consistently high

---

## Coverage Reporting

### Generate Coverage Report

```bash
# HTML report
pytest --cov=tracelet --cov-report=html

# Terminal report
pytest --cov=tracelet --cov-report=term-missing

# XML report (for CI/CD)
pytest --cov=tracelet --cov-report=xml
```

### View HTML Report

```bash
# Open coverage report
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
xdg-open htmlcov/index.html  # Linux
```

### Coverage Targets

| Module | Target | Current |
|--------|--------|---------|
| `core/engine.py` | 90%+ | ~85% |
| `core/worker.py` | 90%+ | ~80% |
| `db/models.py` | 80%+ | ~75% |
| `db/config.py` | 80%+ | ~70% |
| `integration/*.py` | 70%+ | ~65% |
| **Overall** | **80%+** | **~70%** |

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, "3.10", "3.11"]
    
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install pytest pytest-cov
        pip install -e .
    
    - name: Run tests
      run: |
        pytest --cov=tracelet --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
      with:
        file: ./coverage.xml
```

---

## Manual Testing

### Quick Manual Test

```python
import tracelet
from tracelet.core.engine import get_engine

# Initialize
tracelet.init(enabled=True)

# Get engine
engine = get_engine()

# Capture test data
from datetime import datetime, timezone
data = {
    "api_url": "/test/endpoint",
    "start_dt": datetime.now(timezone.utc),
    "end_dt": datetime.now(timezone.utc),
    "elapsed": 0.1,
    "response_status": 200,
    "framework": "test"
}

engine.capture(data)

# Flush buffer
engine.flush_buffer()

# Shutdown
engine.shutdown()
```

### Framework Integration Tests

**Django:**
```bash
cd tests
python test_django.py
```

**FastAPI:**
```bash
cd tests
python test_fastapi.py
```

**Flask:**
```bash
cd tests
python test_flask.py
```

---

## Test Best Practices

### 1. Use Fixtures

```python
@pytest.fixture
def db_config(tmp_path):
    return {"db_url": f"sqlite:///{tmp_path}/test.db"}

def test_something(db_config):
    tracelet.init(db_config=db_config)
    # ... test code ...
```

### 2. Clean Up After Tests

```python
@pytest.fixture(autouse=True)
def reset_settings():
    yield
    # Cleanup after test
    if hasattr(settings, 'engine'):
        engine = get_engine()
        engine.shutdown()
```

### 3. Test Error Cases

```python
def test_error_handling():
    with pytest.raises(RuntimeError):
        # Code that should raise error
        pass
```

### 4. Use Mocks for External Dependencies

```python
from unittest.mock import patch

def test_with_mock():
    with patch('tracelet.core.engine.settings') as mock_settings:
        # Test with mocked settings
        pass
```

---

## Troubleshooting

### Tests Hang/Freeze

**Possible Causes:**
- Thread pool not shutting down
- Queue not being flushed
- Database lock

**Solutions:**
- Ensure `engine.shutdown()` is called
- Check for proper cleanup in fixtures
- Use `max_workers=1` for SQLite tests

### Database Errors

**Possible Causes:**
- Database file locked
- Connection pool exhausted
- Transaction not committed

**Solutions:**
- Use separate database files per test
- Ensure sessions are closed
- Use transactions properly

### Import Errors

**Possible Causes:**
- Missing dependencies
- Circular imports
- Path issues

**Solutions:**
- Install all dependencies: `pip install -e .`
- Check import paths
- Use absolute imports

---

## Performance Benchmarks

### Expected Performance

| Operation | Expected Time | Notes |
|-----------|---------------|-------|
| `capture()` (first call) | ~45ms | Includes initialization |
| `capture()` (subsequent) | ~0.12ms | Non-blocking |
| `flush_buffer()` (50 items) | ~10-50ms | Depends on DB |
| `shutdown()` | ~100-500ms | Waits for tasks |

### Running Benchmarks

```python
import time
import tracelet
from tracelet.core.engine import get_engine

tracelet.init()

engine = get_engine()
start = time.perf_counter()
# ... operation ...
end = time.perf_counter()
print(f"Operation took: {(end-start)*1000:.2f}ms")
```

---

## Contributing Tests

### Adding New Tests

1. **Create test function:**
```python
def test_new_feature():
    # Arrange
    tracelet.init()
    engine = get_engine()
    
    # Act
    result = engine.some_method()
    
    # Assert
    assert result is not None
```

2. **Add to appropriate test class:**
```python
class TestNewFeature:
    def test_new_feature(self):
        # ... test code ...
```

3. **Run tests:**
```bash
pytest tests/test_comprehensive.py::TestNewFeature -v
```

### Test Naming Convention

- Test functions: `test_<feature>_<scenario>`
- Test classes: `Test<Feature>`
- Test files: `test_<module>.py`

---

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- [Tracelet Documentation](../README.md)

---

*Last Updated: January 2025*

