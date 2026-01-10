# Caching Architecture Report

## 1. Introduction: Purpose and Benefits

The Tracelet application heavily relies on database queries for its analytics features. To enhance performance, reduce load on the PostgreSQL database, and provide faster response times to CLI users, a robust caching mechanism has been implemented.

**Key Benefits of Caching:**
- **Improved Response Times:** Frequently accessed data and computational results are served from cache, significantly reducing the time taken for CLI commands to execute.
- **Reduced Database Load:** By minimizing repetitive database queries, caching offloads the database, allowing it to handle more write operations and critical data processing efficiently.
- **Enhanced Scalability:** The caching layer helps Tracelet scale by absorbing read bursts and reducing the need for constant database interaction, making the system more resilient under heavy usage.
- **Cost Efficiency:** Fewer database operations can lead to lower infrastructure costs, especially in cloud-based environments where database usage is often a billing factor.

## 2. Caching Strategies Used

Tracelet employs two primary caching strategies, each tailored to specific use cases:

- **`functools.lru_cache` (Least Recently Used Cache):** This strategy discards the least recently used items first to make space for new ones when the cache is full. It is ideal for functions whose results are frequently re-requested but might have a large variety of inputs.
- **Custom TTL Cache (`ttl_cache_decorator`):** This cache implements a Time-To-Live (TTL) mechanism, where cached data expires after a specified duration. It's suitable for data that is relatively static for a period or where staleness within a defined window is acceptable.

## 3. Design of `tracelet/utils/caching.py`

The `tracelet/utils/caching.py` module encapsulates the caching decorator logic, promoting reusability and separation of concerns.

- **`ttl_cache_decorator(ttl: int)`:**
    - This is a custom decorator that takes a `ttl` (time-to-live in seconds) as an argument.
    - It uses a simple dictionary (`cache = {}`) to store results along with a timestamp.
    - When a function decorated with `ttl_cache_decorator` is called:
        1. It first checks for a `cache_bypass=True` keyword argument. If present, the function is executed directly, bypassing the cache.
        2. If `cache_bypass` is `False` (default), it generates a unique key for the arguments using `functools._make_key`.
        3. It checks if the key exists in the cache and if the cached entry is still valid (current time - timestamp < ttl).
        4. If a valid cached entry is found, it returns the cached result.
        5. Otherwise, the original function is executed, its result is stored in the cache with the current timestamp, and then returned.
- **`lru_cache_decorator(maxsize: int = 128)`:**
    - This decorator is a wrapper around Python's built-in `functools.lru_cache`.
    - It also accepts a `maxsize` argument to limit the number of items in the cache.
    - Similar to `ttl_cache_decorator`, it includes logic to check for a `cache_bypass=True` keyword argument to allow bypassing the LRU cache.
    - If `cache_bypass` is `False`, it calls the `functools.lru_cache`-wrapped function.

The `cache_bypass` mechanism in both decorators is crucial for providing control over when caching should be ignored, particularly for debugging or when fresh data is explicitly required (e.g., via a CLI option).

## 4. Integration of Caching in `tracelet/utils/analytics.py`

The `AnalyticsEngine` in `tracelet/utils/analytics.py` is responsible for interacting with the database to fetch and process raw telemetry data. Several methods within this engine utilize the `ttl_cache_decorator` to cache frequently requested data:

- `AnalyticsEngine.fetch_data_time_range()`: Caches the boundary timestamps for available telemetry data.
- `AnalyticsEngine.fetch_active_endpoints()`: Caches the list of all endpoints that have recorded performance data.
- `AnalyticsEngine.fetch_batch_summary_stats()`: Caches aggregated summary statistics for multiple endpoints over a time window.
- `AnalyticsEngine.fetch_batch_apdex_scores()`: Caches Apdex scores for multiple endpoints.
- `AnalyticsEngine.fetch_batch_window_metrics()`: Caches calculated deltas between two snapshots for multiple endpoints.

All these methods are decorated with `@ttl_cache_decorator(ttl=300)`, meaning their results are cached for 300 seconds (5 minutes). They also accept a `cache_bypass: bool = False` argument, which allows a caller to explicitly bypass the cache for that specific invocation.

Additionally, the pure mathematical function `estimate_percentile()` uses `@lru_cache_decorator(maxsize=128)` to cache its results. This function performs linear interpolation for percentile calculations based on `HistogramSnapshot` objects. Since `HistogramSnapshot` objects are immutable (dataclass with `frozen=True`), and the list of snapshots is converted to a tuple before being passed to `estimate_percentile`, its arguments are hashable, making it suitable for `lru_cache`.

## 5. Integration of Caching in `tracelet/utils/services.py`

The `AnalyticsService` in `tracelet/utils/services.py` orchestrates the `AnalyticsEngine` and performs higher-level business logic. The caching is integrated at this layer as well:

- **`AnalyticsService._parse_window()`:** This method, responsible for parsing duration strings into `TimeWindow` objects, is decorated with `@lru_cache_decorator(maxsize=128)`. This prevents repetitive parsing and validation of time window strings for common durations. It also accepts `cache_bypass: bool = False`.

- **Propagation of `no_cache` argument:** The main entry point for analytics reports, `AnalyticsService.generate_operational_report()`, accepts a `no_cache: bool = False` argument. This argument is then strategically passed down to all underlying cached methods:
    - `self._parse_window(duration_str, cache_bypass=no_cache)`
    - `self.engine.fetch_active_endpoints(cache_bypass=no_cache)`
    - `self.engine.fetch_batch_summary_stats(..., cache_bypass=no_cache)`
    - `self.engine.fetch_batch_apdex_scores(..., cache_bypass=no_cache)`
    - `self.engine.fetch_batch_window_metrics(..., cache_bypass=no_cache)`
    - `estimate_percentile(..., cache_bypass=no_cache)`

This ensures that a single `no_cache` flag at the service layer can effectively disable caching across the entire analytics processing pipeline for a given request.

## 6. Architectural Flow Diagram

The following Mermaid diagram illustrates the flow of a CLI command and how the caching mechanism is integrated:

```mermaid
graph TD
    A[CLI Command] --> B{AnalyticsService.generate_operational_report}
    B -- no_cache=True --> C{Bypass Cache}
    B -- no_cache=False --> D{Check Cache}

    D --> E{Cache Hit}
    E --> F[Return Cached Data]
    D --> G{Cache Miss}

    G --> H{AnalyticsService._parse_window}
    H --> I{AnalyticsEngine Methods (TTL Cache)}
    I --> J{estimate_percentile (LRU Cache)}

    C --> H
    H --> I
    I --> J

    J --> K[Fetch Fresh Data from DB]
    K --> L{Store in Cache}
    L --> F
    F --> M[Display Report]
```

## 7. Key Considerations

-   **Cache Invalidation:**
    -   For `ttl_cache_decorator`, invalidation is time-based. Entries automatically become stale after their `ttl` expires. This is suitable for data that can tolerate a small degree of staleness.
    -   For `lru_cache_decorator`, invalidation occurs when the cache reaches its `maxsize` and older, less frequently used items are discarded. This is effective for functions with dynamic inputs where only the most recent or popular results need to be kept.
    -   The `cache_bypass` argument provides a direct mechanism for manual invalidation or to force fetching fresh data, overriding any active cache.

-   **Hashability:**
    -   For `functools.lru_cache` (and by extension, `lru_cache_decorator`), all arguments to the decorated function must be hashable. This means mutable types like lists cannot be directly used as arguments. In Tracelet, this is handled by converting lists to tuples (e.g., `tuple(buckets)`) before passing them to `estimate_percentile` to ensure hashability.
    -   The custom `ttl_cache_decorator` also uses `functools._make_key`, which requires hashable arguments. Therefore, the same consideration applies.

## 8. How the `no-cache` CLI Option Functions

The Tracelet CLI application (`tui/cli_app.py`) provides a `--no-cache` (or `-nc`) option for several commands, including `status`, `describe`, `top`, and `list_endpoints`.

When a user executes a CLI command with this option (e.g., `tracelet describe --no-cache`):
1. The `typer.Option` in `cli_app.py` captures the `no_cache` flag as `True`.
2. This `no_cache=True` argument is then passed to the `AnalyticsService.generate_operational_report()` method (or `AnalyticsService.engine.fetch_active_endpoints()` for `list_endpoints`).
3. As detailed in Section 5, `generate_operational_report` propagates this `no_cache=True` flag to all subsequent cached function calls within `AnalyticsService` and `AnalyticsEngine`, effectively setting `cache_bypass=True` for all relevant caching decorators.
4. Consequently, all cached functions involved in generating that specific report will bypass their caches and fetch fresh data directly from the PostgreSQL database, providing the most up-to-date information at the expense of potentially longer execution times.
