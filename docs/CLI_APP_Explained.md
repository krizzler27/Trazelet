# Tracelet CLI Design & UI Explained

---

## Design Philosophy

**Goal:** Make analytics **beautiful + functional + fast**

Three principles:
1. **Visual Hierarchy** — Most important info first
2. **Color Coding** — Instant status recognition (red=bad, green=good)
3. **Multiple Formats** — Different use cases need different views

---

## The UI Stack

### Libraries Used

```python
import typer              # CLI framework (argument parsing, commands)
from rich.console import Console  # Terminal output
from rich.table import Table      # Pretty tables
from rich.panel import Panel      # Bordered boxes
from rich.spinner import Spinner  # Loading animations
from rich.live import Live        # Real-time updates
```

### Color Scheme

```python
# Grades (Health Status)
"A" → bold green   (✓ Excellent)
"B" → bold yellow  (△ Good)
"C" → bold orange  (⚠ Fair)
"D" → bold red     (✗ Poor)

# Latency (milliseconds)
< 100ms  → green   (Fast)
< 300ms  → yellow  (Medium)
< 1000ms → orange  (Slow)
> 1000ms → red     (Very Slow)

# Error Rate (percentage)
< 1%   → green   (Excellent)
< 5%   → yellow  (Good)
< 10%  → orange  (Fair)
> 10%  → red     (Poor)
```

---

## Each Command & Its UI

### 1. `tracelet status` — Health Overview

**Purpose:** Quick health check at a glance

**UI Components:**

```
┌─ SPINNER (Loading feedback) ─────────────────┐
│ ⠋ Analyzing last_24h...                      │
└──────────────────────────────────────────────┘
         ↓ (data loaded)
         
┌─ PANEL (Status Summary) ──────────────────────┐
│ ✅ All Systems Operational                    │
│ 8/10 endpoints healthy                        │
└──────────────────────────────────────────────┘

┌─ TABLE (Detailed Metrics) ────────────────────┐
│ Grade │ Endpoint         │ P99 │ Err% │ RPS   │
├───────┼──────────────────┼─────┼──────┼───────┤
│ 🟢 A  │ GET /api/users   │ 89  │ 0.5  │ 150   │
│ 🟡 B  │ POST /api/orders │ 450 │ 3.2  │ 45    │
│ 🟠 C  │ GET /analytics   │ 850 │ 8.5  │ 12    │
│ 🔴 D  │ POST /process    │2450 │15.2  │ 5     │
└───────┴──────────────────┴─────┴──────┴───────┘

┌─ BAR CHART (Grade Distribution) ──────────────┐
│ 🟢 A ████████░░░░░░░░░░░░░░ 4 (40%)          │
│ 🟡 B ████░░░░░░░░░░░░░░░░░░ 2 (20%)          │
│ 🟠 C ██░░░░░░░░░░░░░░░░░░░░ 1 (10%)          │
│ 🔴 D ██░░░░░░░░░░░░░░░░░░░░ 1 (10%)          │
└───────────────────────────────────────────────┘
```

**Code Design:**

```python
@app.command()
def status(duration: str = typer.Option("last_24h", "--duration", "-d")):
    """Quick health overview"""
    
    # 1. Show loading spinner
    with Live(Panel(Spinner(...)), ...):
        # 2. Fetch data (blocking)
        report, window = service.generate_operational_report(duration)
    
    # 3. Calculate grade distribution
    grades = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
    for m in report:
        grades[m.health_grade] += 1
    
    # 4. Show status panel
    # 5. Show detailed table
    # 6. Show grade distribution bars
```

**User Command:**
```bash
tracelet status
tracelet status -d last_24h
tracelet status -d "7 days"
```

---

### 2. `tracelet describe` — Detailed Analytics

**Purpose:** Full metrics breakdown with flexible sorting/filtering

**UI Components:**

```
┌─ TITLE ──────────────────────────────────────┐
│ 📊 Tracelet Analytics — Last 7 Days          │
└──────────────────────────────────────────────┘

┌─ DETAILED TABLE (All Metrics) ────────────────┐
│ Grade │ Endpoint         │ P50 │ P95 │ P99 │  │
├───────┼──────────────────┼─────┼─────┼─────┤  │
│ 🟢 A  │ GET /api/users   │ 12  │ 45  │ 89  │  │
│ 🟡 B  │ POST /api/users  │ 78  │ 200 │ 450 │  │
│ 🟠 C  │ GET /analytics   │ 120 │ 500 │1200 │  │
│ 🔴 D  │ POST /process    │ 450 │1800 │2450 │  │
└───────┴──────────────────┴─────┴─────┴─────┘  │

[Color-coded cells: green=fast, red=slow]
```

**Three Output Formats:**

#### a) TABLE (Default)
```bash
tracelet describe -d last_7d --format table
```

Best for: **Spreadsheet analysis, all metrics visible**

```
Grade | Endpoint         | P50 | P95 | P99 | Err% | RPS | Apdex
------|------------------|-----|-----|-----|------|-----|------
🟢 A  | GET /api/users   | 12  | 45  | 89  | 0.5% | 150 | 0.98
🟡 B  | POST /api/users  | 78  | 200 | 450 | 3.2% | 45  | 0.87
```

#### b) COMPACT
```bash
tracelet describe -d last_7d --format compact
```

Best for: **Quick scans, terminal-friendly**

```
🟢 GET /api/users         | P99: 89ms   | Err: 0.5%  | A
🟡 POST /api/users        | P99: 450ms  | Err: 3.2%  | B
🟠 GET /api/analytics     | P99: 1200ms | Err: 8.5%  | C
🔴 POST /api/process      | P99: 2450ms | Err: 15.2% | D
```

#### c) JSON
```bash
tracelet describe -d last_7d --format json
```

Best for: **Integration, automation, external tools**

```json
{
  "window": {
    "label": "Last 7 Days",
    "start": "2025-01-02T10:30:00+00:00",
    "end": "2025-01-09T10:30:00+00:00"
  },
  "metrics": [
    {
      "path": "/api/users",
      "method": "GET",
      "percentiles": {"p50_ms": 12, "p95_ms": 45, "p99_ms": 89},
      "health": {"error_rate_percent": 0.5, "apdex_score": 0.98, "grade": "A"}
    }
  ]
}
```

**Sorting Options:**

```bash
tracelet describe --sort p99      # Sort by slowest
tracelet describe --sort error    # Sort by highest error rate
tracelet describe --sort rps      # Sort by throughput
tracelet describe --sort apdex    # Sort by user satisfaction
```

**Filtering:**

```bash
tracelet describe -e 1            # Only endpoint ID 1
tracelet describe -d last_24h -e 5  # Only endpoint 5, last 24h
```

---

### 3. `tracelet top` — Anomalies & Outliers

**Purpose:** Find problem endpoints quickly

**UI Components:**

```
🐢 Slowest Endpoints (P99) — Last 7 Days

1. POST /api/process
    P99: 2450ms | Error: 2.3% | Apdex: 0.64 | Grade: 🔴 D

2. GET /api/analytics
    P99: 890ms | Error: 1.2% | Apdex: 0.82 | Grade: 🟡 B

3. POST /api/webhook-retry
    P99: 750ms | Error: 0.8% | Apdex: 0.88 | Grade: 🟡 B
```

**Three Views:**

```bash
# Find slowest endpoints
tracelet top -m p99 -n 10

# Find highest error rates
tracelet top -m error -n 5

# Find slowest (same as p99)
tracelet top -m slowest -n 5
```

**Use Cases:**
- DevOps: "Find endpoints that need optimization"
- On-call: "What's broken right now?"
- Capacity: "Where's the bottleneck?"

---

### 4. `tracelet list` — Endpoint Inventory

**Purpose:** Discover and filter monitored endpoints

**UI Components:**

```
┌─ TABLE (Simple) ──────────────────────────┐
│ ID │ Method │ Path              │Framework│
├────┼────────┼───────────────────┼─────────┤
│ 1  │ GET    │ /api/users        │ fastapi │
│ 2  │ POST   │ /api/users        │ fastapi │
│ 3  │ GET    │ /api/products     │ django  │
│ 4  │ POST   │ /api/orders       │ flask   │
└────┴────────┴───────────────────┴─────────┘
```

**Filtering:**

```bash
tracelet list                        # All endpoints
tracelet list --framework fastapi    # Only FastAPI
tracelet list --method GET          # Only GET requests
tracelet list -f django -m POST     # POST in Django apps
```

---

## Design Patterns Used

### 1. **Spinner for Loading**

```python
with Live(
    Panel(
        Spinner("dots", text="[cyan]Analyzing last_7d...[/cyan]"),
        border_style="cyan"
    ),
    console=console,
    refresh_per_second=1
) as live:
    # Blocking query happens here
    report, window = service.generate_operational_report(duration)
    # Spinner automatically disappears when done
```

**Why:** Visual feedback during network/DB delays (200-500ms)

---

### 2. **Color Gradients**

```python
def _format_latency(ms: float) -> str:
    """Format with color based on severity"""
    if ms < 100:
        return f"[green]{ms:.0f}ms[/green]"     # Good
    elif ms < 300:
        return f"[yellow]{ms:.0f}ms[/yellow]"   # Okay
    elif ms < 1000:
        return f"[orange1]{ms:.0f}ms[/orange1]" # Slow
    else:
        return f"[red]{ms:.0f}ms[/red]"         # Bad
```

**Effect:** Users instantly see "how bad" a metric is by color

---

### 3. **Grade Emojis**

```python
def _get_grade_emoji(grade: str) -> str:
    return {
        "A": "🟢",  # Green circle
        "B": "🟡",  # Yellow circle
        "C": "🟠",  # Orange circle
        "D": "🔴"   # Red circle
    }.get(grade, "⚪")
```

**Effect:** Even without reading the letter, users see health status

---

### 4. **Panels (Bordered Boxes)**

```python
from rich.panel import Panel

# Status panel
Panel(
    "All Systems Operational\n8/10 endpoints healthy",
    title="✅ Health Report: Last 24 Hours",
    border_style="green",
    expand=False
)
```

**Visual hierarchy:** Important info gets a border

---

### 5. **Bar Charts (ASCII)**

```python
for grade in ['A', 'B', 'C', 'D']:
    count = grades[grade]
    pct = (count / len(report) * 100) if report else 0
    bar = "█" * count + "░" * (len(report) - count)
    
    console.print(f"  {grade} {bar} {count} ({pct:.0f}%)")

# Output:
# A ████████░░░░░░░░ 8 (40%)
# B ████░░░░░░░░░░░░ 4 (20%)
# C ██░░░░░░░░░░░░░░ 2 (10%)
# D ██░░░░░░░░░░░░░░ 2 (10%)
```

**Why:** Humans understand proportions faster than numbers

---

## Overall CLI Architecture

```
┌─────────────────────────────────────┐
│ User Types Command                  │
│ (tracelet status -d last_7d)        │
└──────────┬──────────────────────────┘
           │
┌──────────▼──────────────────────────┐
│ Typer Parses Arguments              │
│ ├─ command: "status"                │
│ ├─ duration: "last_7d"              │
│ └─ format: "table" (default)        │
└──────────┬──────────────────────────┘
           │
┌──────────▼──────────────────────────┐
│ Show Loading Spinner                │
│ (gives feedback to user)            │
└──────────┬──────────────────────────┘
           │
┌──────────▼──────────────────────────┐
│ Query Database                      │
│ (service.generate_operational_...) │
└──────────┬──────────────────────────┘
           │
┌──────────▼──────────────────────────┐
│ Format Data for Display             │
│ ├─ Pick UI components              │
│ ├─ Apply color gradients           │
│ ├─ Add emojis & borders            │
│ └─ Sort/filter as requested        │
└──────────┬──────────────────────────┘
           │
┌──────────▼──────────────────────────┐
│ Render to Console                   │
│ ├─ Table with colors               │
│ ├─ Panels with borders             │
│ ├─ Bar charts                      │
│ └─ Summary stats                   │
└──────────┬──────────────────────────┘
           │
┌──────────▼──────────────────────────┐
│ User Sees Beautiful Output ✨        │
└─────────────────────────────────────┘
```

---

## UI Decision Tree

```
User types command:
    ↓
Is this "status"?
    ├─ Yes → Show: Panel + Table + Grade Bar Chart
    └─ No → continue
    
Is this "describe"?
    ├─ Yes → Check format:
    │         ├─ table → Full detail table (all metrics)
    │         ├─ compact → One-liner per endpoint
    │         └─ json → JSON export
    └─ No → continue

Is this "top"?
    ├─ Yes → Ranked list with details
    └─ No → continue

Is this "list"?
    ├─ Yes → Simple inventory table
    └─ No → continue

Is this "health"?
    ├─ Yes → Minimal status summary
    └─ No → unknown command
```

---

## Color Application Examples

### In Tables

```
Endpoint | P99    | Grade
---------|--------|-------
/users   | [green]45[/green] | [green]A[/green]
/orders  | [red]2450[/red]   | [red]D[/red]
```

### In Bars

```python
# Error rate bar
if error_rate < 1:      color = "green"
elif error_rate < 5:    color = "yellow"
elif error_rate < 10:   color = "orange1"
else:                   color = "red"

console.print(f"Error: [{color}]{error_rate:.2f}%[/{color}]")
```

### In Panels

```python
if critical_count > 0:
    border_style = "red"      # Critical issues → red border
elif warning_count > 0:
    border_style = "yellow"   # Warnings → yellow border
else:
    border_style = "green"    # All good → green border
```

---

## Why This Design Works

| Design Choice | Benefit |
|---------------|---------|
| **Spinner** | Users know system is working (not hung) |
| **Color gradients** | Instant visual severity assessment |
| **Emojis** | Universal symbols (no language barrier) |
| **Multiple formats** | Covers: human reading, automation, export |
| **Panels & borders** | Visual hierarchy shows importance |
| **Bar charts** | Proportion understanding (not just numbers) |
| **Sorted by default** | Most important (slow/error) endpoints first |

---

## Example: Full Workflow

```bash
$ tracelet status -d last_24h

⠋ Analyzing last_24h...

✅ All Systems Operational
8/10 endpoints healthy

┏━━━━━━┳━━━━━━━━━━━━━━━━┳━━━┳━━━━┳━━━━┳━━━━━┳━━━━┳━━━━┓
┃Grade ┃Endpoint        ┃P50┃P95 ┃P99 ┃Err% ┃RPS ┃Apdx┃
┡━━━━━━╇━━━━━━━━━━━━━━━━╇━━━╇━━━━╇━━━━╇━━━━━╇━━━━╇━━━━┩
│🟢 A  │GET /api/users  │ 12│ 45 │ 89 │0.5% │150 │0.98│
│🟡 B  │POST /api/data  │ 78│200 │450 │3.2% │ 45 │0.87│
│🟠 C  │GET /analytics  │120│500 │1200│8.5% │ 12 │0.70│
│🔴 D  │POST /process   │450│1800│2450│15.2%│ 5  │0.45│
└──────┴────────────────┴───┴────┴────┴─────┴────┴────┘

Grade Distribution:
  🟢 A ████████░░░░░░░░░░░░░░ 4 (50%)
  🟡 B ████░░░░░░░░░░░░░░░░░░ 2 (25%)
  🟠 C ██░░░░░░░░░░░░░░░░░░░░ 1 (12%)
  🔴 D ██░░░░░░░░░░░░░░░░░░░░ 1 (12%)

$
```

**What user sees:**
- ✅ Green checkmark = everything is good (at top)
- ✓ Numbers at a glance (50% A-grade endpoints)
- ✓ Distribution clearly visible
- ✓ Problem endpoint (D grade) highlighted in red
- ✓ All in <1 second

---

## Summary

The CLI design philosophy:

```
Data (boring numbers)
    ↓ (Apply formatting)
Information (color, emoji, charts)
    ↓ (Apply context)
Knowledge (user instantly understands)
```

Every UI choice serves the goal: **Make operational insights obvious at a glance.**
