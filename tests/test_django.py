import os
import time
from django.conf import settings
import django
import tracelet

db_config = {} #! Setup Db Config before Running
tracelet.init(max_workers=2, enabled=True, db_config=db_config)

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY="test-key",
        ROOT_URLCONF=__name__,
        # 1. Add this to fix the AppLabel error
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'rest_framework',
        ],
        # 2. Add a dummy database so DRF has a place to "look" for models
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        MIDDLEWARE=[
            "django.middleware.common.CommonMiddleware",
            "tracelet.integration.django.DjangoMiddleware", 
        ],
    )
# 2. INITIALIZE DJANGO
django.setup()

from django.conf import settings
from django.core.management import execute_from_command_line
from django.http import JsonResponse
from django.urls import path
from rest_framework.response import Response
from rest_framework.decorators import api_view

# 2. DEFINING THE SAME ROUTES AS FASTAPI/FLASK

def root(request):
    """Basic fast route to test SUCCESS status."""
    return JsonResponse({"message": "Tracelet is watching Django"})

def slow_api(request):
    """Simulates a 3s delay."""
    time.sleep(3)
    return JsonResponse({"status": "completed", "waited": "3s"})

def trigger_error(request):
    """Simulates a 500 Server Error."""
    return JsonResponse({"error": "Simulated Server Crash"}, status=500)

def not_found(request):
    """Simulates a 404 missing resource."""
    return JsonResponse({"detail": "Resource missing"}, status=404)

@api_view(['POST'])
def create_item(request):
    """Tests POST request handling via DRF."""
    name = request.data.get("name", "Unknown")
    return Response({"message": f"Item {name} created", "data": request.data})

def compute(request, number):
    """Simulates CPU work and tests normalization."""
    result = sum(i * i for i in range(number))
    return JsonResponse({"result": result})

# 3. URL PATTERNS (The "Normalization" test)
urlpatterns = [
    path("", root),
    path("slow", slow_api),
    path("error", trigger_error),
    path("not-found", not_found),
    path("items", create_item),
    path("heavy-compute/<int:number>", compute), # Normalization: /heavy-compute/<int:number>
]

if __name__ == "__main__":
    print("\n--- Django running on http://127.0.0.1:7001 ---")
    execute_from_command_line(["manage.py", "runserver", "7001"])