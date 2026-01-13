# Contributing to Tracelet

This project is a work in progress, and your insight is the missing piece. Whether you've found a bug, have a feature you're dying to see, or just want to tackle a 'Good First Issue', your contribution makes this project better for everyone.

---

## 🤝 Contribution Workflow

To ensure code quality and consistency, please follow these steps for any contribution:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes** (follow PEP8, add tests)
4. **Run tests** (`pytest`)
5. **Commit your changes** (`git commit -m 'Add amazing feature'`)
6. **Push to the branch** (`git push origin feature/amazing-feature`)
7. **Open a Pull Request**

---

## ⚙️ Development Environment Setup

To set up your local development environment:

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/tracelet.git
cd tracelet

# 2. Install uv (if needed)
# On macOS and Linux.
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows.
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# With pip.
pip install uv

# 3. Sync everything
# Install the project in development mode
# This creates the .venv, installs dependencies, and enables the --extras
uv sync --extra dev
```

### Running Tests & Benchmarks

```bash
# Run all tests
pytest

# Run with coverage report (aiming for 80%+)
pytest --cov=tracelet --cov-report=html
```

Refer [Testing report](docs/testing_report.md) for more documentation.

### Tracelet Architecture

The Tracelet Analytics System is a high-performance solution for Python API monitoring, designed with a modular architecture that logically groups components into two primary modules: the Data Ingestion & Persistence Module and the Analytics & User Interface Module. This structure ensures clear separation of concerns, scalability, and maintainability.

* Data Ingestion & Persistence Module
* Analytics & User Interface Module

Refer [Architecture report](docs/architecture_report.md) for more documentation.

### Project Structure

```
src
├── tracelet
│   ├── __init__.py
│   ├── config.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── worker.py
│   ├── db
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── models.py
│   ├── integrations
│   │   ├── __init__.py
│   │   ├── django.py
│   │   ├── fastapi.py
│   │   ├── flask.py
│   ├── tui
│   │   ├── analytics.py
│   │   ├── app.py
│   │   ├── caching.py
│   │   ├── services.py
│   ├── utils
│   │   ├── helper.py
│   │   ├── logger_config.py
```

---

## 🛠️ Code Standards & Quality Targets

Tracelet is striving for production-grade code quality. Adherence to these standards is mandatory for contributions:

* **PEP8 Compliance**: General Python style guide adherence.
* **Type Hinting**: Target **90%+ coverage**. Use type hints for all public functions and methods.
* **Docstrings**: Document all public methods using a standard format (e.g., Google style), clearly detailing parameters, return values, and exceptions.
* **Test Coverage**: Target **80%+ coverage**. Add unit and integration tests for all new functionality.
* **Error Handling**: Use custom Tracelet exceptions rather than generic `Exception` catches where appropriate.

---

### Roadmap and Feature Tracking

For our development roadmap and detailed feature tracking, please refer to [Tracker.md](Tracker.md).
