# Tracelet Query & Processing Flow - Explained

---

## The Three Key Concepts

### 1. CAPTURING (Data Collection)

**What happens when a request hits your API:**

```
User Request → Your FastAPI Middleware
                    ↓
              1. Record request_time
              2. Let request execute
              3. Record response_time
              4. Calculate latency_ms = response_time - request_time
                    ↓
              Store in Metrics table:
              ├─ endpoint_id = 1
              ├─ request_time = 2025-01-09 10:00:00+00:00
              ├─ response_time = 2025-01-09 10:00:0.045+00:00  (45ms later)
              ├─ latency_ms = 45.0
              ├─ response_status = SUCCESS
              └─ created_at = 2025-01-09 10:00:0.045+00:00
```

**Real Example:**
```python
# Your middleware does this:
start = time.time()
response = await next(request)  # Execute the actual endpoint
end = time.time()

latency_ms = (end - start) * 1000

# Store in DB
metric = Metrics(
    endpoint_id=1,
    latency_ms=45.0,
    response_status="success",
    created_at=datetime.now(timezone.utc)
)
session.add(metric)
session.commit()
```

So **Metrics table** = Raw individual request data (every single request)

```
Metrics Table (After 1 hour of traffic):
id  | endpoint_id | latency_ms | created_at              | status
----|-------------|------------|-------------------------|--------
1   | 1           | 45.2       | 2025-01-09 10:00:00     | success
2   | 1           | 52.1       | 2025-01-09 10:00:05     | success
3   | 1           | 48.9       | 2025-01-09 10:00:10     | success
... [3600 rows for 1 hour] ...
3600| 1           | 120.5      | 2025-01-09 10:59:59     | failed
```

---

### 2. BUCKETING (Grouping into Buckets)

**Every 5 minutes, we create a SNAPSHOT:**

We take all metrics from that window and **count how many fit in each bucket**.

```
Time Window: 10:00 - 10:05 AM

All requests in this window:
├─ 45ms ✓
├─ 52ms ✓
├─ 48ms ✓
├─ 120ms ✓
├─ 89ms ✓
├─ 210ms ✓
├─ 450ms ✓
└─ 95ms ✓

Total = 8 requests

Now count how many fit in EACH bucket:
  le=10ms:    0 requests (none that fast)
  le=25ms:    0 requests
  le=50ms:    2 requests (45ms, 48ms fit here)
  le=100ms:   4 requests (45, 48, 52, 89, 95ms all fit)
  le=250ms:   7 requests (all except 450ms)
  le=500ms:   8 requests (all fit here)
  le=inf:     8 requests (all fit here)
```

**Store as Buckets Snapshot:**
```
Buckets Table @ 10:05 AM:
endpoint_id | le  | count | captured_at
------------|-----|-------|------------------------
1           | 10  | 0     | 2025-01-09 10:05:00+00:00
1           | 25  | 0     | 2025-01-09 10:05:00+00:00
1           | 50  | 2     | 2025-01-09 10:05:00+00:00
1           | 100 | 4     | 2025-01-09 10:05:00+00:00
1           | 250 | 7     | 2025-01-09 10:05:00+00:00
1           | 500 | 8     | 2025-01-09 10:05:00+00:00
1           | inf | 8     | 2025-01-09 10:05:00+00:00
```

Next 5 minutes (10:05 - 10:10):
```
New metrics:
├─ 38ms ✓
├─ 65ms ✓
├─ 155ms ✓
├─ 72ms ✓
└─ 500ms ✓

Total = 4 more requests

Buckets Table @ 10:10 AM:
endpoint_id | le  | count | captured_at
------------|-----|-------|------------------------
1           | 10  | 0     | 2025-01-09 10:10:00+00:00
1           | 25  | 0     | 2025-01-09 10:10:00+00:00
1           | 50  | 2     | 2025-01-09 10:10:00+00:00  (38ms fits here)
1           | 100 | 4     | 2025-01-09 10:10:00+00:00  (38, 65, 72ms)
1           | 250 | 5     | 2025-01-09 10:10:00+00:00  (+ 155ms)
1           | 500 | 6     | 2025-01-09 10:10:00+00:00  (+ 500ms)
1           | inf | 6     | 2025-01-09 10:10:00+00:00
```

**Key insight:** Each row in Buckets = "How many requests so far fit in this bucket?"

---

### 3. DELTA (Time Window Calculation)

**When user runs: `tracelet describe -d 7 days`**

We need to know: "How many requests in EACH bucket for the last 7 days?"

**But we can't scan 430K raw metrics** — too slow!

Instead, we use **snapshot subtraction**:

```
User asks: "Give me data for Jan 8 - Jan 9 (yesterday + today)"

Step 1: Find two snapshots
  ├─ Start snapshot (latest snapshot ≤ Jan 8 00:00)
  │  └─ @ Jan 8 23:55:00
  └─ End snapshot (latest snapshot ≤ Jan 9 23:59:59)
     └─ @ Jan 9 23:55:00

Step 2: Get bucket counts from BOTH snapshots

Snapshot @ Jan 8 23:55:00:
  le=100ms: count = 50,000 requests total so far
  le=500ms: count = 145,000 requests total so far

Snapshot @ Jan 9 23:55:00:
  le=100ms: count = 65,000 requests total so far
  le=500ms: count = 175,000 requests total so far

Step 3: Calculate DELTA (difference)
  Delta for le=100ms:  65,000 - 50,000 = 15,000 NEW requests ≤ 100ms
  Delta for le=500ms: 175,000 - 145,000 = 30,000 NEW requests ≤ 500ms

Result: In that 24-hour window, 15,000 requests were fast, 30,000 were slow
```

**Why this works:**

- ✅ **Fast**: Only 2 snapshot queries, not 430K metric queries
- ✅ **Accurate**: Subtraction gives us exact window counts
- ✅ **Scalable**: Works for any time range

---

## Real Query Example

### User Command:
```bash
tracelet describe -d last_7d
```

### What Happens Behind the Scenes:

#### STEP 1: Parse Time Window
```python
# service._parse_window("last_7d")
now = datetime.now(timezone.utc)  # 2025-01-09 10:30:00+00:00
start = now - timedelta(days=7)   # 2025-01-02 10:30:00+00:00

print(f"Query window: {start} → {now}")
# Query window: 2025-01-02 10:30:00+00:00 → 2025-01-09 10:30:00+00:00
```

#### STEP 2: Get Active Endpoints
```python
# engine.fetch_active_endpoints()

SELECT DISTINCT
    te.endpoint_id,
    te.path,
    te.method,
    te.framework
FROM tracelet_endpoints te
JOIN tracelet_latency_buckets tlb ON te.endpoint_id = tlb.endpoint_id
ORDER BY te.path, te.method

# Result: [(1, '/api/users', 'GET', 'fastapi'), (2, '/api/users', 'POST', 'fastapi'), ...]
```

#### STEP 3: Get Snapshot Deltas for EACH Endpoint
```python
# engine.get_window_metrics(endpoint_id=1, start=2025-01-02 10:30, end=2025-01-09 10:30)

# Sub-step 3a: Find START snapshot
SELECT MAX(captured_at)
FROM tracelet_latency_buckets
WHERE endpoint_id = 1
  AND captured_at <= 2025-01-02 10:30:00
# Result: 2025-01-02 10:25:00 (closest snapshot before start)

# Sub-step 3b: Find END snapshot
SELECT MAX(captured_at)
FROM tracelet_latency_buckets
WHERE endpoint_id = 1
  AND captured_at <= 2025-01-09 10:30:00
# Result: 2025-01-09 10:25:00 (closest snapshot before end)

# Sub-step 3c: Get counts from START snapshot
SELECT le, count
FROM tracelet_latency_buckets
WHERE endpoint_id = 1 AND captured_at = 2025-01-02 10:25:00

# Result:
# le=10,    count=0
# le=25,    count=0
# le=50,    count=12,000
# le=100,   count=45,000
# le=250,   count=105,000
# le=500,   count=150,000
# le=1000,  count=205,000
# le=2500,  count=290,000
# le=5000,  count=310,000
# le=inf,   count=320,000

# Sub-step 3d: Get counts from END snapshot
SELECT le, count
FROM tracelet_latency_buckets
WHERE endpoint_id = 1 AND captured_at = 2025-01-09 10:25:00

# Result:
# le=10,    count=15,000
# le=25,    count=18,000
# le=50,    count=42,000
# le=100,   count=95,000
# le=250,   count=210,000
# le=500,   count=330,000
# le=1000,  count=435,000
# le=2500,  count=610,000
# le=5000,  count=650,000
# le=inf,   count=680,000

# Sub-step 3e: Calculate DELTA
deltas = [
    (le=10,    delta=15,000 - 0 = 15,000),
    (le=25,    delta=18,000 - 0 = 18,000),
    (le=50,    delta=42,000 - 12,000 = 30,000),
    (le=100,   delta=95,000 - 45,000 = 50,000),
    (le=250,   delta=210,000 - 105,000 = 105,000),
    (le=500,   delta=330,000 - 150,000 = 180,000),
    (le=1000,  delta=435,000 - 205,000 = 230,000),
    (le=2500,  delta=610,000 - 290,000 = 320,000),
    (le=5000,  delta=650,000 - 310,000 = 340,000),
    (le=inf,   delta=680,000 - 320,000 = 360,000)
]

# This means in the 7-day window:
# - 15,000 requests were ≤ 10ms
# - 30,000 requests were ≤ 50ms (including the 15,000 from above)
# - 50,000 requests were ≤ 100ms
# - 360,000 total requests (all of them)
```

#### STEP 4: Calculate Percentiles
```python
# estimate_percentile(deltas, percentile=95)

total = 360,000
target_rank = (95 / 100) * 360,000 = 342,000

# Find which bucket contains the 342,000th request
cumulative = 0
for le, count in deltas:
    cumulative += count
    if cumulative >= target_rank:
        # P95 is in this bucket
        # Use linear interpolation to get exact value
        break

# Result: P95 = 387.5ms (95% of requests were faster than 387.5ms)
```

#### STEP 5: Calculate Other Metrics
```python
# Get from raw metrics (in the time window)
SELECT 
    AVG(latency_ms) = 156.3ms,
    MAX(latency_ms) = 8523.2ms,
    COUNT(*) = 360,000,
    COUNT(*) FILTER (WHERE response_status='failed') = 8,500

error_rate = (8,500 / 360,000) * 100 = 2.36%
throughput = 360,000 / (7 days in seconds) = 595.2 RPS
apdex = (satisfactory + tolerable/2) / total = 0.87
```

#### STEP 6: Assign Grade
```python
p99 = 2450ms
error_rate = 2.36%
apdex = 0.87

# Grade logic:
if p99 < 200 and error_rate < 1 and apdex >= 0.95:
    grade = "A"
elif p99 < 500 and error_rate < 5 and apdex >= 0.85:  # ✓ This matches!
    grade = "B"
else:
    grade = "C" or "D"

# Result: GRADE = B (Good)
```

#### STEP 7: Display
```
GET /api/users
├─ P50: 89ms
├─ P95: 245ms
├─ P99: 2450ms
├─ Error: 2.36%
├─ RPS: 595.2
├─ Apdex: 0.87
└─ Grade: B 🟡
```

---

## Summary Flowchart

```
Raw Metrics (Every Request)
    ↓
    └─→ Middleware captures request/response times
    └─→ Stores in Metrics table (430K rows for 7 days)
    
Every 5 Minutes
    ↓
    └─→ Count how many requests fit in each bucket
    └─→ Store as Buckets snapshot
    
When User Queries (Last 7 Days)
    ↓
    ├─→ Find start snapshot (Jan 2)
    ├─→ Find end snapshot (Jan 9)
    ├─→ Subtract: Jan 9 counts - Jan 2 counts = DELTAS
    ├─→ Interpolate to find P50, P95, P99
    ├─→ Calculate error rate, RPS, Apdex from raw metrics
    └─→ Assign grade based on composite metrics
    
Display to User
    ↓
    └─→ Beautiful table with colors & emojis
```

---

## Key Insights

| Concept | What It Is | Example |
|---------|-----------|---------|
| **Capturing** | Recording every request | 360,000 requests in 7 days |
| **Bucketing** | Grouping requests by speed | "50,000 requests were ≤100ms" |
| **Delta** | Change between two snapshots | "From Jan 2 to Jan 9: +15,000 fast requests" |
| **Percentile** | "X% of requests faster than Y ms" | "95% faster than 387ms" |
| **Grade** | Overall health (A/B/C/D) | "B = Good" |

---

## Why This Architecture?

**Without snapshots (naive approach):**
```
User asks: "Data for last 7 days"
System: "Scan 430,000 metrics... calculating... (5 seconds)"
User: "Why is this so slow?"
```

**With snapshots (smart approach):**
```
User asks: "Data for last 7 days"
System: "Find 2 snapshots, subtract... (50 milliseconds)"
User: "Wow, instant!"
```

**That's the whole point:** Snapshots make analytics **instantly fast** even with millions of metrics.
