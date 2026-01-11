from typing import Tuple, Dict, Any, Callable
import functools
import time

def ttl_cache_decorator(ttl: int):
    """
    A decorator that caches the results of a function with a Time-To-Live (TTL).

    Args:
        ttl (int): The time in seconds after which the cache entry expires.

    Example:
        @ttl_cache_decorator(ttl=300)
        def fetch_data(cache_bypass: bool = False):
            # Function implementation
        
        # Use cache (default)
        result = fetch_data()
        
        # Bypass cache (force fresh data)
        result = fetch_data(cache_bypass=True)

    Note:
        The cache_bypass parameter is consumed by the decorator and not passed
        to the underlying function. This allows bypassing the cache when needed.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        cache: Dict[Tuple, Tuple[Any, float]] = {}

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if kwargs.pop("cache_bypass", False):
                return func(*args, **kwargs)

            key = functools._make_key(args, kwargs, typed=False)
            if key in cache:
                result, timestamp = cache[key]
                if time.time() - timestamp < ttl:
                    return result
            
            result = func(*args, **kwargs)
            cache[key] = (result, time.time())
            return result
        return wrapper
    return decorator

def lru_cache_decorator(maxsize: int = 128):
    """
    A decorator that caches the results of a function using an LRU (Least Recently Used) strategy.

    Args:
        maxsize (int): The maximum number of items to store in the cache.

    Example:
        @lru_cache_decorator(maxsize=128)
        def calculate_percentile(snapshots, percentile, cache_bypass: bool = False):
            # Function implementation
        
        # Use cache (default)
        result = calculate_percentile(snapshots, 50.0)
        
        # Bypass cache (force fresh calculation)
        result = calculate_percentile(snapshots, 50.0, cache_bypass=True)

    Note:
        The cache_bypass parameter is consumed by the decorator and not passed
        to the underlying function. This allows bypassing the cache when needed.
        The underlying functools.lru_cache is thread-safe.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        cached_func = functools.lru_cache(maxsize=maxsize)(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if kwargs.pop("cache_bypass", False):
                return func(*args, **kwargs)
            return cached_func(*args, **kwargs)
        return wrapper
    return decorator
