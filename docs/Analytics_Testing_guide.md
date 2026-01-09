# Tracelet Testing & Data Generation Guide

**Quick Setup:** 5 minutes to full testing environment

---

## Overview

The testing suite generates **realistic API performance data** for testing analytics:

| Table | Records | Description |
|-------|---------|-------------|
| **Endpoints** | 10 | Realistic API paths with latency profiles |
| **Metrics** | 430K+ | Raw request data (30 days) |
| **Buckets** | 51K+ | Histogram snapshots every 5 minutes |

---

## Prerequisites

```bash
pip install numpy  # For realistic latency distributions
```

---

## Quick Start

### Step 1: Generate Test Data (3 minutes)

```bash
# Generate 30 days of realistic data
python scripts/generate_test_data.py

# Or with clearing existing data
python scripts/generate_test_data.py --clear
```

**Output:**
```
✅ Data generation complete!
  Total metrics: 430,520
  Total bucket snapshots: 51,408
  Total snapshots: 8,640
  Date range: 2024-12-16 to 2025-01-15
```

### Step 2: Run Analytics Tests (2 minutes)

```bash
# Run full test suite
python scripts/test_analytics.py

# Or specific tests
python scripts/test_analytics.py --engine       # Test database layer
python scripts/test_analytics.py --service      # Test orchestration
python scripts/test_analytics.py --benchmark    # Performance tests
```

### Step 3: Try CLI Commands (baseline data ready)

```bash
# Quick health check
tracelet status

# Detailed analytics
tracelet describe -d last_7d

# Find slowest endpoints
tracelet top -m p99

# List all endpoints
tracelet list
```

---

## Data Generation Details

### Endpoints Included

| Path | Method | Framework | Latency Profile | Error Rate |
|------|--------|-----------|-----------------|------------|
| `/api/users` | GET | FastAPI | Fast (50ms ±20) | 0.5% |
| `/api/users` | POST | FastAPI | Medium (150ms ±50) | 2.0% |
| `/api/users/<id>` | GET | FastAPI | Fast (45ms ±15) | 0.3% |
| `/api/users/<id>` | PUT | FastAPI | Slow (200ms ±80) | 3.0% |
| `/api/users/<id>` | DELETE | FastAPI | Medium (80ms ±30) | 1.5% |
| `/api/products` | GET | Django | Medium (120ms ±50) | 1.0% |
| `/api/products/<id>` | GET | Django | Medium (100ms ±40) | 0.8% |
| `/api/orders` | POST | Flask | Slow (300ms ±100) | 4.0% |
| `/api/orders` | GET | Flask | Slow (250ms ±80) | 2.5% |
| `/api/analytics/report` | POST | FastAPI | **Very Slow (2s ±0.5s)** | **5.0%** |

### Traffic Patterns

Simulates realistic traffic:

```
Business Hours (9-17):    100-150% traffic (peak)
Evening (17-22):           80-110% traffic
Night (22-6):              20-40% traffic (low)
```

### Bucket Distribution

Each snapshot captures cumulative latency counts:

```
Bucket Thresholds: [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, ∞] ms
Snapshot Interval:  5 minutes
30-Day Data:        8,640 snapshots per endpoint
```

---

## Testing Commands

### Full Test Suite

```bash
python scripts/test_analytics.py
```

**Runs:**
1. ✓ AnalyticsEngine tests (7 methods)
2. ✓ Percentile estimation tests
3. ✓ AnalyticsService tests (high-level API)
4. ✓ Performance benchmarks

---

### Individual Tests

#### Test AnalyticsEngine (Database Layer)

```bash
python scripts/test_analytics.py --engine
```

Tests:
- `fetch_data_time_range()` — Data availability
- `fetch_active_endpoints()` — Endpoint discovery
- `get_window_metrics()` — Delta calculations
- `fetch_batch_summary_stats()` — Batch queries
- `get_error_rate()` — Error calculation
- `get_throughput_rps()` — Throughput calculation
- `get_apdex_score()` — Apdex calculation

---

#### Test Percentile Estimation

```bash
python scripts/test_analytics.py --percentile
```

Tests:
- Linear interpolation (Master Formula)
- P50, P75, P90, P95, P99 calculations
- Edge cases (infinity bucket)

---

#### Test AnalyticsService (Orchestration)

```bash
python scripts/test_analytics.py --service
```

Tests:
- Time window parsing (all formats)
- Operational report generation
- Single endpoint queries
- Grade distribution
- All report fields

---

#### Benchmark Performance

```bash
python scripts/test_analytics.py --benchmark
```

Measures:
- Query time for last 24 hours
- Query time for last 7 days
- Query time for last 30 days
- Query time for last 1 year

---

## Data Management

### View Test Data

```bash
# List all endpoints
python -c "
from tracelet.db.config import SessionLocal
from tracelet.db.models import Endpoints

session = SessionLocal()
for ep in session.query(Endpoints).all():
    print(f'{ep.method:6} {ep.path:30} ({ep.framework})')
session.close()
"
```

### Check Data Coverage

```bash
# Count metrics and buckets
python -c "
from tracelet.db.config import SessionLocal
from tracelet.db.models import Metrics, Buckets, Endpoints

session = SessionLocal()
print(f'Endpoints: {session.query(Endpoints).count()}')
print(f'Metrics:   {session.query(Metrics).count():,}')
print(f'Buckets:   {session.query(Buckets).count():,}')

# Date range
from sqlalchemy import func
m_min = session.query(func.min(Metrics.created_at)).scalar()
m_max = session.query(func.max(Metrics.created_at)).scalar()
print(f'Date range: {m_min} to {m_max}')
session.close()
"
```

### Clear Data

```bash
# Delete all test data
python scripts/generate_test_data.py --cleanup

# Or programmatically
python -c "from scripts.generate_test_data import cleanup_test_data; cleanup_test_data()"
```

---

## CLI Testing Workflows

### Workflow 1: Health Check

```bash
# Quick status
tracelet status -d last_24h

# Expected output:
# - 10 endpoints
# - Health distribution (A/B/C/D grades)
# - Grade: Mostly A/B (good health)
```

### Workflow 2: Detailed Analytics

```bash
# Last 7 days, detailed table
tracelet describe -d last_7d --format table

# Sort by error rate
tracelet describe -d last_7d --sort error

# Export to JSON
tracelet describe -d last_7d --format json > report.json
```

### Workflow 3: Anomaly Detection

```bash
# Top 5 slowest endpoints
tracelet top -m p99 -n 5

# Top 3 highest error rate
tracelet top -m error -n 3

# Expected: /api/analytics/report should be slowest (2000ms)
```

### Workflow 4: Endpoint Inventory

```bash
# List all endpoints
tracelet list

# Filter by framework
tracelet list --framework fastapi

# Filter by method
tracelet list --method GET
```

---

## Expected Test Results

### AnalyticsEngine Tests

```
✓ fetch_data_time_range()       → Data range: 30 days
✓ fetch_active_endpoints()      → 10 endpoints found
✓ get_window_metrics()          → Bucket deltas calculated
✓ fetch_batch_summary_stats()   → Batch query (3 endpoints)
✓ get_error_rate()              → 1.45% (average across all)
✓ get_throughput_rps()          → 180.2 RPS
✓ get_apdex_score()             → 0.82 (good)
```

### Percentile Tests

```
P50: 89ms (median)
P75: 145ms (upper quartile)
P90: 210ms (90th percentile)
P95: 280ms (95th percentile)
P99: 450ms (99th percentile)
```

### AnalyticsService Tests

```
✓ Time window parsing:  5 formats tested
✓ Report generation:   10 endpoints with grades
✓ Grade distribution:  A=3, B=4, C=2, D=1
✓ Single endpoint:     Detailed metrics
```

### Performance Benchmarks

```
Benchmark: generate_operational_report()
  last_24h      ~150ms
  last_7d       ~250ms
  last_30d      ~400ms
  1 year        ~600ms
```

---

## Troubleshooting

### No Data Generated

**Symptom:** "No data available" message

**Causes:**
- Database not initialized
- Tracelet.init() not called in application
- Wrong database connection

**Fix:**
```bash
# Ensure DB is set up
python scripts/generate_test_data.py --clear

# Verify data exists
python -c "from tracelet.db.config import SessionLocal; from tracelet.db.models import Endpoints; print(SessionLocal().query(Endpoints).count())"
```

---

### Tests Timeout

**Symptom:** Tests hang or take >30 seconds

**Causes:**
- Database connection issues
- Large dataset (>1M metrics)
- Slow disk/network

**Fix:**
```bash
# Clear and regenerate smaller dataset
python scripts/generate_test_data.py --cleanup

# Modify scripts/generate_test_data.py:
# DAYS_OF_DATA = 7  # Instead of 30
# METRICS_PER_SNAPSHOT = 50  # Instead of 100
```

---

### CLI Commands Show No Data

**Symptom:** "No metrics data available"

**Causes:**
- Test data not generated
- Wrong database configuration
- Data expired

**Fix:**
```bash
# Check data exists
python scripts/test_analytics.py --service

# If no data, regenerate
python scripts/generate_test_data.py --clear
```

---

## Integration Testing

### Test with Your Application

```python
# In your app after tracelet.init():
from scripts.generate_test_data import generate_test_data

# Generate test endpoints and data
generate_test_data(clear_existing=False)

# Now run your tests
# CLI commands will show realistic data
```

---

## Performance Characteristics

### Data Generation Time

```
10 endpoints × 30 days × 288 snapshots/day
= 86,400 snapshots total
= 430K+ metrics
= ~3-5 minutes to generate
= 50-100MB database size
```

### Query Performance

```
Single endpoint (last 7 days):    <10ms
All endpoints (last 7 days):      200-300ms
All endpoints (last 30 days):     400-600ms
All endpoints (last 1 year):      800-1200ms
```

---

## Next Steps

1. ✅ Generate test data: `python scripts/generate_test_data.py`
2. ✅ Run test suite: `python scripts/test_analytics.py`
3. ✅ Try CLI commands: `tracelet status -d last_7d`
4. ✅ Verify analytics: `tracelet describe --format table`
5. ✅ Run benchmarks: `python scripts/test_analytics.py --benchmark`

---

## Reference

- **Data Generator:** `scripts/generate_test_data.py`
- **Test Suite:** `scripts/test_analytics.py`
- **CLI App:** `tracelet` command
- **Analytics Docs:** See `ANALYTICS_AND_CLI.md`

---

**Ready to test?** Start with:
```bash
python scripts/generate_test_data.py && python scripts/test_analytics.py
```