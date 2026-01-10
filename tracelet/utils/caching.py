
import functools
import time

def ttl_cache_decorator(ttl: int):
    """
    A decorator that caches the results of a function with a Time-To-Live (TTL).

    Args:
        ttl (int): The time in seconds after which the cache entry expires.
    """
    def decorator(func):
        cache = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check for a cache bypass flag in kwargs
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
    """
    def decorator(func):
        cached_func = functools.lru_cache(maxsize=maxsize)(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check for a cache bypass flag in kwargs
            if kwargs.pop("cache_bypass", False):
                return func(*args, **kwargs)
            return cached_func(*args, **kwargs)
        return wrapper
    return decorator
