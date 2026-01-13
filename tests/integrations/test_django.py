import time

import pytest  # type: ignore
import django
from django.conf import settings
from django.http import JsonResponse
from django.test import Client
from django.urls import path

import tracelet


# --- Django + Tracelet setup -----------------------------------------------


def setup_django(db_url: str | None = None) -> None:
    """
    Configure Django settings and initialize Tracelet middleware.

    Safe to call multiple times; configuration only happens once.
    """
    if db_url is None:
        db_url = "sqlite:///tracelet.db"

    db_config = {"db_url": db_url, "echo": False}
    tracelet.init(max_workers=2, enabled=True, db_config=db_config)

    if not settings.configured:
        settings.configure(
            DEBUG=True,
            SECRET_KEY="test-key",
            ROOT_URLCONF=__name__,
            ALLOWED_HOSTS=["testserver", "127.0.0.1"],
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "rest_framework",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            MIDDLEWARE=[
                "django.middleware.common.CommonMiddleware",
                "tracelet.integrations.django.DjangoMiddleware",
            ],
            REST_FRAMEWORK={
                "DEFAULT_RENDERER_CLASSES": [
                    "rest_framework.renderers.JSONRenderer",
                ],
                "DEFAULT_PARSER_CLASSES": [
                    "rest_framework.parsers.JSONParser",
                ],
            },
        )
        django.setup()


# Call setup immediately at module load to prevent import-time decorator failures
setup_django()


# --- Views & URLConf --------------------------------------------------------


def root(request):
    """Basic fast route to test SUCCESS status."""
    return JsonResponse({"message": "Tracelet is watching Django"})


def slow_api(request):
    """Simulates a 3s delay (kept short for tests)."""
    time.sleep(0.01)
    return JsonResponse({"status": "completed", "waited": "3s"})


def trigger_error(request):
    """Simulates a 500 Server Error."""
    return JsonResponse({"error": "Simulated Server Crash"}, status=500)


def not_found(request):
    """Simulates a 404 missing resource."""
    return JsonResponse({"detail": "Resource missing"}, status=404)


# Import DRF components AFTER setup_django()
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["POST"])
def create_item(request):
    """Tests POST request handling via DRF."""
    name = request.data.get("name", "Unknown")
    return Response({"message": f"Item {name} created", "data": request.data})


def compute(request, number):
    """Simulates CPU work and tests normalization."""
    result = sum(i * i for i in range(number))
    return JsonResponse({"result": result})


urlpatterns = [
    path("", root),
    path("slow", slow_api),
    path("error", trigger_error),
    path("not-found", not_found),
    path("items", create_item),
    path("heavy-compute/<int:number>", compute),
]


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
def django_client():
    return Client()


class TestDjangoIntegration:
    """Integration tests for the Django example app."""

    def test_root_endpoint(self, django_client: Client):
        response = django_client.get("/")
        assert response.status_code == 200
        assert response.json()["message"]

    def test_slow_endpoint(self, django_client: Client):
        response = django_client.get("/slow")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_error_endpoint(self, django_client: Client):
        response = django_client.get("/error")
        assert response.status_code == 500
        assert response.json()["error"] == "Simulated Server Crash"

    def test_not_found_endpoint(self, django_client: Client):
        response = django_client.get("/not-found")
        assert response.status_code == 404
        assert response.json()["detail"] == "Resource missing"

    def test_create_item_endpoint(self, django_client: Client):
        payload = {"name": "Widget", "value": 42}
        response = django_client.post(
            "/items", payload, content_type="application/json"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Item Widget created"
        assert data["data"]["name"] == "Widget"

    def test_heavy_compute_endpoint(self, django_client: Client):
        response = django_client.get("/heavy-compute/10")
        assert response.status_code == 200
        assert "result" in response.json()


# --- Manual server entrypoint ----------------------------------------------

if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    print("\n--- Django running on http://127.0.0.1:7001 ---")
    execute_from_command_line(["manage.py", "runserver", "7001"])
