import time

import pytest  # type: ignore
from flask import Flask, abort, jsonify, request

import tracelet
from tracelet.integration.flask import FlaskMiddleware


# --- Application factory ----------------------------------------------------

def create_app(db_url: str | None = None) -> Flask:
    """
    Create a Flask app wired with Tracelet middleware.

    Used by pytest with a lightweight SQLite DB and as a manual demo server.
    """
    if db_url is None:
        db_url = "sqlite:///:memory:"
    db_config = {"db_url": db_url, "echo": False}
    tracelet.init(max_workers=2, enabled=True, db_config=db_config)

    app = Flask(__name__)
    FlaskMiddleware(app=app)

    @app.route("/")
    def root():
        """Basic fast route to test SUCCESS status."""
        return jsonify({"message": "Tracelet is watching Flask"})

    @app.route("/slow")
    def slow_api():
        """Simulates a slow database or external API call (kept short for tests)."""
        time.sleep(0.01)
        return jsonify({"status": "completed", "waited": "3s"})

    @app.route("/error")
    def trigger_error():
        """Simulates a failure to test FAILED status in metrics."""
        abort(500, description="Simulated Server Crash")

    @app.route("/not-found")
    def not_found():
        """Simulates a 404 error."""
        abort(404, description="Resource missing")

    @app.route("/items", methods=["POST"])
    def create_item():
        """Tests POST request handling."""
        data = request.get_json() or {}
        name = data.get("name", "Unknown")
        return jsonify({"message": f"Item {name} created", "data": data})

    @app.route("/heavy-compute/<int:number>")
    def compute(number: int):
        """
        Tests Normalization:
        This should show up as /heavy-compute/<int:number> in your DB.
        """
        result = sum(i * i for i in range(number))
        return jsonify({"result": result})

    return app


# --- Pytest integration tests ----------------------------------------------


@pytest.fixture(autouse=True)
def reset_tracelet_engine():
    """Ensure the Tracelet engine is shut down between tests in this module."""
    yield
    try:
        from tracelet.core.engine import get_engine

        engine = get_engine()
        engine.shutdown()
    except Exception:
        pass


@pytest.fixture
def flask_client():
    app = create_app()
    return app.test_client()


class TestFlaskIntegration:
    """Integration tests for the Flask example app."""

    def test_root_endpoint(self, flask_client):
        response = flask_client.get("/")
        assert response.status_code == 200
        assert response.get_json()["message"]

    def test_slow_endpoint(self, flask_client):
        response = flask_client.get("/slow")
        assert response.status_code == 200
        assert response.get_json()["status"] == "completed"

    def test_error_endpoint(self, flask_client):
        response = flask_client.get("/error")
        assert response.status_code == 500
        assert "Simulated Server Crash" in response.get_data(as_text=True)

    def test_not_found_endpoint(self, flask_client):
        response = flask_client.get("/not-found")
        assert response.status_code == 404
        assert "Resource missing" in response.get_data(as_text=True)

    def test_create_item_endpoint(self, flask_client):
        payload = {"name": "Widget", "value": 42}
        response = flask_client.post("/items", json=payload)
        assert response.status_code == 200
        data = response.get_json()
        assert data["message"] == "Item Widget created"
        assert data["data"]["name"] == "Widget"

    def test_heavy_compute_endpoint(self, flask_client):
        response = flask_client.get("/heavy-compute/10")
        assert response.status_code == 200
        assert "result" in response.get_json()


# --- Manual server entrypoint ----------------------------------------------

if __name__ == "__main__":
    # Running on a different port than FastAPI to avoid conflict
    demo_app = create_app()
    demo_app.run(port=5001, debug=True)