import re
from tracelet import settings
import bisect

def format_as_seconds(duration: float) -> str:
    """Formats a duration in seconds into a human-readable string with appropriate precision."""
    if duration < 0.000001:  # Less than a microsecond
        return f"{duration:.9f}"
    elif duration < 0.001:   # Less than a millisecond
        return f"{duration:.6f}"
    else:
        return f"{duration:.3f}"

def clean_url_path(path: str) -> str:
    """Normalizes and sanitizes a URL path for consistent tracing and aggregation."""
    if not path:
        return "/"
    
    # 1. Standardize Slashes
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")

    # 2. The "Normalization" Step (The Missing Feature)
    # This catches IDs/UUIDs if the framework didn't already normalize them
    # Replace UUIDs with <uuid>
    path = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<uuid>', path)
    
    # 3. Replace Numeric IDs with <id>
    # (Matches digits between slashes or at the end of a string)
    path = re.sub(r'/\d+(?=/|$)', '/<id>', path)
    
    # 4. Security Masking (Basic)
    # If there are query params left or sensitive words in path

    sensitive_patterns = ['token', 'auth', 'secret', 'password']
    for word in sensitive_patterns:
        if word in path:
            # Basic masking logic
            path = re.sub(rf'{word}/[^/]+', f'{word}/<masked>', path)

    return path

def get_latency_bucket(latency_ms: float) -> float:
    """Determines the appropriate latency bucket for a given latency value."""
    index = bisect.bisect_left(settings.BUCKET_THRESHOLDS, latency_ms)
    return settings.BUCKET_THRESHOLDS[index]