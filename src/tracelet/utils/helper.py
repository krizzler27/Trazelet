import re
from tracelet import settings
import bisect

# Constants for URL cleaning and formatting
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
ID_PATTERN = re.compile(r"/\d+(?=/|$)")

# Common sensitive keywords to mask in URL paths
SENSITIVE_KEYWORDS = [
    "token",
    "auth",
    "secret",
    "password",
    "api_key",
    "apikey",
    "key",
    "credentials",
    "session",
    "sessionid",
    "jwt",
    "private_key",
]

# Regex pattern that matches any of the sensitive keywords preceded by start or slash,
# followed by a separator (/ or =) and then any non-separator characters.
# The lookbehind (?<=^|/) ensures we match "key" but not "monkey".
# Note: We use a capturing group for the keyword and separator to reconstruct the path.
SENSITIVE_RE = re.compile(
    rf"(^|/)({'|'.join(SENSITIVE_KEYWORDS)})([/=])[^/]+", re.IGNORECASE
)

MICROSECOND_THRESHOLD = 0.000001
MILLISECOND_THRESHOLD = 0.001


def format_as_seconds(duration: float) -> str:
    """Formats a duration in seconds into a human-readable string with appropriate precision."""
    if duration < MICROSECOND_THRESHOLD:  # Less than a microsecond
        return f"{duration:.9f}"
    elif duration < MILLISECOND_THRESHOLD:  # Less than a millisecond
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

    # 2. The "Normalization" Step
    # This catches IDs/UUIDs if the framework didn't already normalize them
    # Replace UUIDs with <uuid>
    path = UUID_PATTERN.sub("<uuid>", path)

    # 3. Replace Numeric IDs with <id>
    # (Matches digits between slashes or at the end of a string)
    path = ID_PATTERN.sub("/<id>", path)

    # 4. Security Masking (Improved)
    # Mask values following sensitive keywords (e.g., /token/abc or /token=abc)
    path = SENSITIVE_RE.sub(r"\1\2\3<masked>", path)

    return path


def get_latency_bucket(latency_ms: float) -> float:
    """Determines the appropriate latency bucket for a given latency value."""
    index = bisect.bisect_left(settings.BUCKET_THRESHOLDS, latency_ms)
    return settings.BUCKET_THRESHOLDS[index]
