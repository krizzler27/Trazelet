import asyncio

import pytest  # type: ignore
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

import tracelet
from tracelet.integrations.fastapi import FastAPIMiddleware


# --- Application factory ----------------------------------------------------

class Item(BaseModel):
    name: str
    description: str | None = None
    price: float


def create_app(db_url: str | None = None) -> FastAPI:
    """
    Create a FastAPI app wired with Tracelet middleware.

    Used both by pytest (with a lightweight SQLite DB) and by the
    manual demo server (optionally with PostgreSQL).
    """
    if db_url is None:
        # Lightweight default for tests: in-memory SQLite
        db_url = "sqlite:///:memory:"

    db_config = {
        "db_url": db_url,
        "echo": False,
    }
    tracelet.init(max_workers=2, enabled=True, db_config=db_config, logger_level='debug')

    app = FastAPI(title="Tracelet Test Suite")
    app.add_middleware(FastAPIMiddleware)

    @app.get("/")
    def root():
        """Basic fast route to test SUCCESS status."""
        return {"message": "Sentinel is watching"}

    @app.get("/slow")
    async def slow_api():
        """Simulates a slow database or external API call (3 seconds)."""
        await asyncio.sleep(3)  # keep unit tests fast
        return {"status": "completed", "waited": "3s"}

    @app.get("/error")
    def trigger_error():
        """Simulates a failure to test FAILED status in metrics."""
        raise HTTPException(status_code=500, detail="Simulated Server Crash")

    @app.get("/not-found")
    def not_found():
        """Simulates a 404 error."""
        raise HTTPException(status_code=404, detail="Resource missing")

    @app.post("/items")
    def create_item(item: Item):
        """Tests POST request handling."""
        return {"message": f"Item {item.name} created", "data": item}

    @app.get("/heavy-compute/{number}")
    def compute(number: int):
        """Simulates CPU-bound work to see how latency is tracked."""
        result = sum(i * i for i in range(number))
        return {"result": result}

    return app


# --- Pytest integration tests ----------------------------------------------


@pytest.fixture(autouse=True)
def reset_tracelet_engine():
    """
    Ensure the Tracelet engine is shut down between tests in this module.
    """
    yield
    try:
        from tracelet.core.engine import get_engine  # local import to avoid cycles

        engine = get_engine()
        engine.shutdown()
    except Exception:
        # If engine was never initialized, that's fine.
        pass


@pytest.fixture
def fastapi_client():
    app = create_app()
    return TestClient(app)


class TestFastAPIIntegration:
    """Integration tests for the FastAPI example app."""

    def test_root_endpoint(self, fastapi_client: TestClient):
        response = fastapi_client.get("/")
        assert response.status_code == 200
        assert response.json()["message"]

    def test_slow_endpoint(self, fastapi_client: TestClient):
        response = fastapi_client.get("/slow")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    def test_error_endpoint(self, fastapi_client: TestClient):
        response = fastapi_client.get("/error")
        assert response.status_code == 500
        assert response.json()["detail"] == "Simulated Server Crash"

    def test_not_found_endpoint(self, fastapi_client: TestClient):
        response = fastapi_client.get("/not-found")
        assert response.status_code == 404
        assert response.json()["detail"] == "Resource missing"

    def test_create_item_endpoint(self, fastapi_client: TestClient):
        payload = {"name": "Widget", "description": "Test item", "price": 9.99}
        response = fastapi_client.post("/items", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Item Widget created"
        assert data["data"]["name"] == "Widget"

    def test_heavy_compute_endpoint(self, fastapi_client: TestClient):
        response = fastapi_client.get("/heavy-compute/10")
        assert response.status_code == 200
        assert "result" in response.json()


# --- Manual server entrypoint ----------------------------------------------

if __name__ == "__main__":
    # Quick manual test server, using PostgreSQL by default.
    import uvicorn

    USER = "USER"
    PASSWORD = "PASSWORD"
    postgres_db_url = f"postgresql+psycopg2://{USER}:{PASSWORD}@localhost:5432/tracelet"

    demo_app = create_app(db_url=postgres_db_url)
    uvicorn.run(demo_app, host="127.0.0.1", port=8012)