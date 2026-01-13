"""
Test suite for caching decorators to verify correctness and cache_bypass functionality.
"""

import pytest  # type: ignore
import time
from tracelet.tui.caching import ttl_cache_decorator, lru_cache_decorator


def test_ttl_cache_basic():
    """Test basic TTL caching functionality."""
    call_count = [0]  # Use list to allow modification in nested function

    @ttl_cache_decorator(ttl=1)
    def cached_function(x: int) -> int:
        call_count[0] += 1
        return x * 2

    # First call - should execute function
    result1 = cached_function(5)
    assert result1 == 10
    assert call_count[0] == 1

    # Second call - should use cache
    result2 = cached_function(5)
    assert result2 == 10
    assert call_count[0] == 1  # Should not increment

    # Different argument - should execute function
    result3 = cached_function(10)
    assert result3 == 20
    assert call_count[0] == 2


def test_ttl_cache_expiration():
    """Test that TTL cache expires after TTL period."""
    call_count = [0]

    @ttl_cache_decorator(ttl=1)  # 1 second TTL
    def cached_function(x: int) -> int:
        call_count[0] += 1
        return x * 2

    # First call
    result1 = cached_function(5)
    assert call_count[0] == 1

    # Immediate second call - should use cache
    result2 = cached_function(5)
    assert call_count[0] == 1

    # Wait for TTL to expire
    time.sleep(1.1)

    # Third call - should execute function again
    result3 = cached_function(5)
    assert call_count[0] == 2
    assert result3 == 10


def test_ttl_cache_bypass():
    """Test that cache_bypass flag forces fresh data."""
    call_count = [0]

    @ttl_cache_decorator(ttl=300)  # Long TTL
    def cached_function(x: int, cache_bypass: bool = False) -> int:
        call_count[0] += 1
        return x * 2

    # First call - should execute
    result1 = cached_function(5)
    assert call_count[0] == 1

    # Second call - should use cache
    result2 = cached_function(5)
    assert call_count[0] == 1

    # Third call with cache_bypass=True - should execute again
    result3 = cached_function(5, cache_bypass=True)
    assert call_count[0] == 2
    assert result3 == 10

    # Fourth call without bypass - should use cache again
    result4 = cached_function(5)
    assert call_count[0] == 2  # Should still be 2 (from cache)


def test_lru_cache_basic():
    """Test basic LRU caching functionality."""
    call_count = [0]

    @lru_cache_decorator(maxsize=2)
    def cached_function(x: int) -> int:
        call_count[0] += 1
        return x * 2

    # First call
    result1 = cached_function(5)
    assert result1 == 10
    assert call_count[0] == 1

    # Second call - should use cache
    result2 = cached_function(5)
    assert result2 == 10
    assert call_count[0] == 1  # Still 1 (cached)

    # Different argument
    result3 = cached_function(10)
    assert result3 == 20
    assert call_count[0] == 2  # Cache: {5, 10}

    # Another different argument (exceeds maxsize=2, evicts 5)
    result4 = cached_function(15)
    assert result4 == 30
    assert call_count[0] == 3  # Cache: {10, 15} (5 evicted)

    # Call first argument again - was evicted, so executes again
    result5 = cached_function(5)
    assert result5 == 10
    assert call_count[0] == 4  # Cache: {15, 5} (10 evicted, 5 added)

    # Call 15 again - should still be cached (most recently used)
    result6 = cached_function(15)
    assert result6 == 30
    assert call_count[0] == 4  # Should use cache (15 is in cache)


def test_lru_cache_bypass():
    """Test that cache_bypass flag works with LRU cache."""
    call_count = [0]

    @lru_cache_decorator(maxsize=128)
    def cached_function(x: int, cache_bypass: bool = False) -> int:
        call_count[0] += 1
        return x * 2

    # First call
    result1 = cached_function(5)
    assert call_count[0] == 1

    # Second call - should use cache
    result2 = cached_function(5)
    assert call_count[0] == 1

    # Third call with cache_bypass=True - should execute again
    result3 = cached_function(5, cache_bypass=True)
    assert call_count[0] == 2
    assert result3 == 10


def test_cache_with_kwargs():
    """Test that caching works correctly with keyword arguments."""
    call_count = [0]

    @ttl_cache_decorator(ttl=300)
    def cached_function(x: int, y: int = 0, cache_bypass: bool = False) -> int:
        call_count[0] += 1
        return x + y

    # First call
    result1 = cached_function(5, y=10)
    assert result1 == 15
    assert call_count[0] == 1

    # Second call with same args - should use cache
    result2 = cached_function(5, y=10)
    assert result2 == 15
    assert call_count[0] == 1

    # Different kwargs - should execute
    result3 = cached_function(5, y=20)
    assert result3 == 25
    assert call_count[0] == 2


def test_cache_bypass_doesnt_modify_original_kwargs():
    """Test that cache_bypass doesn't break if function also uses kwargs."""
    call_count = [0]

    @ttl_cache_decorator(ttl=300)
    def cached_function(x: int, **kwargs) -> int:
        call_count[0] += 1
        # Simulate function that might check for cache_bypass
        if kwargs.get("some_other_param"):
            return x + kwargs["some_other_param"]
        return x * 2

    # This should work - cache_bypass is popped before function call
    result1 = cached_function(5, cache_bypass=True, some_other_param=10)
    assert result1 == 15
    assert call_count[0] == 1

    # Call again - should execute (cache_bypass was True, so not cached)
    result2 = cached_function(5, some_other_param=10)
    assert call_count[0] == 2


def test_multiple_instances_dont_share_cache():
    """Test that different function instances have separate caches."""
    call_count1 = [0]
    call_count2 = [0]

    @ttl_cache_decorator(ttl=300)
    def function1(x: int) -> int:
        call_count1[0] += 1
        return x * 2

    @ttl_cache_decorator(ttl=300)
    def function2(x: int) -> int:
        call_count2[0] += 1
        return x * 3

    # Call both functions
    function1(5)
    function2(5)

    assert call_count1[0] == 1
    assert call_count2[0] == 1

    # Call again - both should use their own caches
    function1(5)
    function2(5)

    assert call_count1[0] == 1  # Still 1 (cached)
    assert call_count2[0] == 1  # Still 1 (cached)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
