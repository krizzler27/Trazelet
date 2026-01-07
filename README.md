# Tracelet

<div align="center">

**A Lightweight, Cross-Framework APM for Python**

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code Quality](https://img.shields.io/badge/code%20quality-9.0%2F10-brightgreen.svg)](Audit_report.md)
[![Test Coverage](https://img.shields.io/badge/coverage-70%25-yellow.svg)](Testing_report.md)

*Zero-configuration performance insights for FastAPI, Django, and Flask*

[Features](#-features) • [Quick Start](#-quick-start) • [Documentation](#-documentation) • [Contributing](#-contributing)

</div>

---

## 🎯 What is Tracelet?

**Tracelet** is a high-performance, open-source Python library designed to give backend developers **instant visibility** into their API's performance without the complexity of heavy enterprise tools.

### The Problem It Solves

Most developers don't know their API is slow until a user complains. Enterprise tools (like New Relic, Datadog) are too expensive or hard to set up for small-to-medium projects. Tracelet fills this gap by being **local, private, and lightweight**.

### Why Tracelet?

- 🚀 **Near-Zero Overhead**: Non-blocking design with <0.2ms average latency impact
- 🔒 **Privacy-First**: All data stays on your machine. No cloud, no external services
- 🎯 **Zero Configuration**: Works out of the box with sensible defaults
- 🔌 **Framework Agnostic**: Works seamlessly with FastAPI, Django, and Flask
- ⚡ **Production-Ready**: Thread-safe, battle-tested architecture

---

## ✨ Features

### Core Capabilities

- ✅ **Automatic Request Tracking**: Captures latency, status codes, and API paths
- ✅ **Non-Blocking Architecture**: Queue-based buffering ensures zero impact on response times
- ✅ **Batch Processing**: Configurable batching for high-performance metric storage
- ✅ **Thread-Safe**: Verified with 100+ concurrent operations
- ✅ **Invisible Middleware**: Never crashes your application, graceful error handling
- ✅ **Local Storage**: SQLite (default) or PostgreSQL support
- ✅ **Route Normalization**: Automatically normalizes dynamic paths (`/user/123` → `/user/<id>`)

### Framework Support

- ✅ **FastAPI**: Clean ASGI middleware integration
- ✅ **Django**: Standard middleware pattern
- ✅ **Flask**: Proper request tracking with `g` object

### Performance Metrics

- **Capture Latency**: ~0.12ms average (non-blocking)
- **Concurrent Operations**: Thread-safe, zero errors in 100+ concurrent captures
- **Database Writes**: Background processing, no impact on request path
- **Memory Footprint**: Minimal, efficient queue-based buffering

---

## 🚀 Quick Start

### Installation

```bash
# Core installation
pip install tracelet

# With framework support (optional)
pip install tracelet[fastapi]  # For FastAPI
pip install tracelet[flask]     # For Flask
pip install tracelet[django]   # For Django
```

### Basic Usage

#### FastAPI

```python
from fastapi import FastAPI
from tracelet.integration.fastapi import FastAPIMiddleware
import tracelet

# Initialize Tracelet (uses SQLite by default)
tracelet.init()

app = FastAPI()
app.add_middleware(FastAPIMiddleware)

@app.get("/")
def read_root():
    return {"message": "Hello World"}
```

#### Django

```python
# settings.py
MIDDLEWARE = [
    # ... other middleware ...
    "tracelet.integration.django.DjangoMiddleware",
]

# Initialize Tracelet
import tracelet
tracelet.init()
```

#### Flask

```python
from flask import Flask
from tracelet.integration.flask import FlaskMiddleware
import tracelet

tracelet.init()

app = Flask(__name__)
app.wsgi_app = FlaskMiddleware(app=app)

@app.route("/")
def hello():
    return "Hello World!"
```

### Custom Configuration

```python
import tracelet

# Custom database and settings
tracelet.init(
    db_config={
        "db_url": "postgresql+psycopg2://user:pass@localhost:5432/tracelet",
        "echo": False
    },
    batch_size=100,           # Batch size for bulk inserts
    flush_interval=5.0,        # Flush interval in seconds
    max_workers=3,            # Background worker threads
    use_bulk_mode=True,       # Enable bulk insert mode
    logger_level="INFO"       # Logging level
)
```

---

## 📊 What Gets Tracked?

Tracelet automatically captures:

- **API Path**: Normalized route patterns (e.g., `/user/<id>` instead of `/user/123`)
- **Latency**: Request start/end times and elapsed duration
- **Status Codes**: HTTP response status codes
- **Framework**: Identifies which framework handled the request
- **Timestamps**: Precise request/response timestamps

**Example Metrics:**

```
/api/users/123     | 45ms  | 200 | FastAPI | 2025-01-15 10:30:00
/api/users/456     | 120ms | 200 | FastAPI | 2025-01-15 10:30:01
/api/orders/789    | 15ms  | 404 | FastAPI | 2025-01-15 10:30:02
```

---

## 🏗️ Architecture

### Design Principles

1. **Non-Blocking**: All database operations happen in background threads
2. **Thread-Safe**: Uses `ThreadPoolExecutor` and thread-safe queues
3. **Invisible**: Never crashes your application, all errors are caught and logged
4. **Efficient**: Batch processing reduces database overhead

### How It Works

```
Request → Middleware → Queue → Background Worker → Database
         (<0.2ms)    (O(1))   (Async)            (Batched)
```

1. **Request arrives** → Middleware captures start time
2. **Response sent** → Middleware captures end time and queues metric
3. **Background worker** → Processes queue in batches
4. **Database** → Bulk inserts for performance

---

## 📖 Documentation

### Configuration Options

| Parameter          | Type  | Default    | Description                                                         |
| ------------------ | ----- | ---------- | ------------------------------------------------------------------- |
| `db_config`      | dict  | `None`   | Database configuration (uses SQLite if not provided)                |
| `enabled`        | bool  | `True`   | Enable/disable Tracelet tracking                                    |
| `batch_size`     | int   | `50`     | Number of metrics to batch before flushing                          |
| `flush_interval` | float | `5.0`    | Maximum seconds to wait before flushing queue data to DB            |
| `max_workers`    | int   | `1`      | Background worker threads (1 for SQLite, configurable for Postgres) |
| `use_bulk_mode`  | bool  | `True`   | Enable bulk insert mode for performance                             |
| `logger_level`   | str   | `"INFO"` | Logging level: DEBUG, INFO, WARNING, ERROR                          |

### Database Configuration

#### SQLite (Default)

```python
tracelet.init()  # Uses SQLite automatically
```

#### PostgreSQL

```python
tracelet.init(
    db_config={
        "db_url": "postgresql+psycopg2://user:password@localhost:5432/dbname",
        "echo": False
    },
    max_workers=3  # Multiple workers for better throughput
)
```

### Advanced Usage

#### Disable Tracelet Temporarily

```python
tracelet.init(enabled=False)  # Disables tracking without removing middleware
```

#### Custom Logging

```python
tracelet.init(logger_level="DEBUG")  # More verbose logging
```

#### Manual Flush

```python
from tracelet.core.engine import get_engine

engine = get_engine()
engine.flush_buffer()  # Manually flush queued metrics
```

---

## 🧪 Testing

Tracelet includes a comprehensive test suite with ~70% coverage:

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests
pytest

# Run with coverage
pytest --cov=tracelet --cov-report=html
```

See [Testing_report.md](Testing_report.md) for detailed test documentation.

---

## 🛠️ Development

### Project Structure

```
tracelet/
├── __init__.py          # Public API
├── config.py            # Configuration management
├── core/
│   ├── engine.py        # Core engine (singleton)
│   └── worker.py        # Background worker (ThreadPoolExecutor)
├── db/
│   ├── config.py        # Database configuration
│   └── models.py        # SQLAlchemy models
├── integration/
│   ├── django.py        # Django middleware
│   ├── fastapi.py       # FastAPI middleware
│   └── flask.py         # Flask middleware
└── utils/
    └── helper.py        # Utility functions
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_comprehensive.py

# Run with verbose output
pytest -v
```

### Code Quality

- **Test Coverage**: ~70% (Target: 80%+)
- **Type Hints**: ~40% (Target: 90%+)
- **Code Quality Score**: 9.0/10 (See [Audit_report.md](Audit_report.md))

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### How to Contribute

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes** (follow PEP8, add tests)
4. **Run tests** (`pytest`)
5. **Commit your changes** (`git commit -m 'Add amazing feature'`)
6. **Push to the branch** (`git push origin feature/amazing-feature`)
7. **Open a Pull Request**

### Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/tracelet.git
cd tracelet

# Install in development mode
pip install -e ".[fastapi,flask,django]"

# Install test dependencies
pip install pytest pytest-cov

# Run tests
pytest
```

### Code Style

- Follow PEP8 guidelines
- Use type hints where possible
- Add docstrings to public methods
- Write tests for new features

---

## 📋 Roadmap

### v0.9.0 - Beta Release (Current)

- ✅ Core features complete
- ✅ Comprehensive test suite
- ✅ Framework integrations
- 🔴 LICENSE file (TODO)
- 🟡 Increase test coverage to 80%+

### v1.0.0 - Public Release

- 🟡 Export to CSV/JSON
- 🟡 Basic Dashboard
- 🟡 Slack/Email Alerts
- 🟡 API Endpoint for Metrics

### v1.1.0 - Growth Features

- 🟢 CLI Tool
- 🟢 Performance Grading System
- 🟢 Custom Tags/Labels
- 🟢 Data Masking

See [Tracker.md](Tracker.md) for detailed roadmap and feature tracking.

---

## 📝 License

*License information will be added soon. (MIT License recommended)*

---

## 🙏 Acknowledgments

- Built with ❤️ for the Python community
- Inspired by the need for lightweight, privacy-first APM tools
- Thanks to all contributors and testers

---

## 📚 Additional Resources

- [Audit Report](Audit_report.md) - Comprehensive technical audit
- [Testing Report](Testing_report.md) - Test suite documentation
- [Tracker](Tracker.md) - Development roadmap and feature tracking

---

## 💬 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/tracelet/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/tracelet/discussions)

---

<div align="center">

**Made with ❤️ by the Tracelet Team**

[⭐ Star us on GitHub](https://github.com/yourusername/tracelet) • [📖 Documentation](#-documentation) • [🐛 Report Bug](https://github.com/yourusername/tracelet/issues)

</div>
