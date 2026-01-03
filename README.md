# Tracelet

---

## **Tracelet: A Lightweight, Cross-Framework APM**

**Tracelet** is a performance monitoring library (APM) for Python developers. It provides high-visibility insights into web application health with **zero configuration** and  **near-zero overhead** .

### **What it does:**

* **Automatic Route Tracking:** Automatically detects and normalizes API paths (e.g., turning `/user/542` into `/user/<id>`) across different frameworks.
* **Latency Monitoring:** Measures exact request-to-response time using high-precision performance counters.
* **Status Intelligence:** Tracks success and failure rates across your entire backend ecosystem.
* **Non-Blocking Engine:** Uses an asynchronous "ghost process" (background threading) to ensure that monitoring your app never slows down your users.

### **The "Solid" Architecture:**

Tracelet is designed with a  **Unified Adapter Pattern** , allowing it to speak the native language of the three most popular Python frameworks simultaneously:

1. **FastAPI** (via ASGI Middleware)
2. **Flask** (via WSGI Request Hooks)
3. **Django** (via the Middleware Onion Pipeline)

---

### **Why it’s different:**

Unlike heavy enterprise tools, **Tracelet** is built for developers who want to own their data. It stores metrics in your own database, allowing for custom analytics without the privacy concerns or high costs of third-party SaaS platforms.

> Current Status: Version 1.0 supports multi-framework adapters, centralized SQL engine, and automated route normalization.

---

# Tracelet: Development Roadmap

**Project Status:** 🟢 Core Logic Complete

**Allowed Tech Stack:** FastAPI, Flask, Django, DRF, Ninja, Strawberry, SQLite, Postgres.

**Folder Structure:**

---
├─ core
      └─ engine.py
      └─ __init__.py
  ├─ db
      └─ config.py
      └─ models.py
      └─ __init__.py
  ├─ integration
      └─ django.py
      └─ fastapi.py
      └─ flask.py
      └─ __init__.py
  ├─ tests
      └─ test_django.py
      └─ test_fastapi.py
      └─ test_flask.py
  ├─ utils
      └─ helper.py
  └─ tracelet.db
  └─ tracelet.db-shm
  └─ tracelet.db-wal
---
*To make it indestructible.*

* [ ] **The Batch Buffer (Performance):** * Implement `ThreadSafeBuffer`.
  * Add a logic to "flush" metrics to the DB only when the count hits 50 OR 10 seconds have passed.
* [X] **SQLite Concurrency (WAL Mode):** * Force `PRAGMA journal_mode=WAL;` on SQLite connections to prevent "Database is locked" errors during high traffic.
* [ ] **Masker Class (Privacy):** * Build a utility to scrub sensitive headers (e.g., `Authorization`, `Cookie`) and body fields (e.g., `password`, `credit_card`) before they hit the DB.

---

## 📊 Phase 2: Intelligence & Configuration

*Turning raw data into useful insights.*

* [ ] **Threshold Logic:** * Add a `TRACELET_THRESHOLD_MS` config. If set to `200`, Tracelet ignores all requests faster than 200ms (saves DB space).
* [ ] **Response Type Detection:** * Capture the `Content-Type` header to categorize endpoints into **API** (JSON) vs **Fullstack** (HTML/Template).
* [ ] **Error Correlation:** * Automatically flag and group routes that return `5xx` status codes for a "High Priority" report.
* [ ] **Framework Metadata:** * Store specific versions (e.g., `FastAPI 0.109.0`) in the `APIs` table for better debugging.

---

## 🛠️ Phase 3: The "Wow" Factor (The Interface)

*Building the tools that developers actually interact with.*

* [ ] **The Tracelet CLI:** * Use `Typer` and `Rich` to build a terminal dashboard.
  * Command: `tracelet report --last 24h` (Prints a beautiful table of slow routes).
* [ ] Performance Grading System: * Implement an algorithm that assigns grades:
  * Grade A: < 100ms
  * Grade B: 100ms - 500ms
  * Grade F: > 1s (The "Fix This Now" list).
* [ ] **Export Features:** * Allow exporting metrics to `.csv` or `.json` for external analysis.

---

## 📦 Phase 4: Launch & Ecosystem

*Sharing Tracelet with the world.*

* [ ] **PyPI Packaging:** * Structure the project with `pyproject.toml`.
  * Ensure all 3 adapters are easily importable: `from tracelet.integrations.django import TraceletMiddleware`.
* [ ] **The "Zero-Config" Documentation:** * Write a one-page README showing how to add Tracelet in  **3 lines of code** .
* [ ] **Community Outreach:** * **Reddit (r/Python):** "I built a unified APM for every major Python framework."
  * **Hacker News:** Focus on the "Privacy-First" / "No-SaaS" aspect.

---

## 🔮 Future Research (Backlog)

* [ ] **Background Worker Integration:** Support for Celery/RQ task monitoring.
* [ ] **Export to OpenTelemetry:** Allow Tracelet to "hand off" data to larger tools like Grafana if the user grows out of it.
* [ ] **Real-Time Web Dashboard:** A tiny, built-in FastAPI dashboard to see live graphs.

---
