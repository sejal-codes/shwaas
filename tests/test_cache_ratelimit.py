from app.cache import TTLCache
from app.ratelimit import RateLimiter


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now


def test_cache_returns_then_expires():
    clock = Clock()
    cache = TTLCache(10, 5, clock)
    cache.set("a", 1)
    assert cache.get("a") == 1
    clock.now = 11
    assert cache.get("a") is None


def test_cache_is_size_capped():
    cache = TTLCache(100, 2)
    for key in "abc":
        cache.set(key, key)
    assert cache.get("a") is None and cache.get("c") == "c"


def test_rate_limiter_blocks_then_recovers():
    clock = Clock()
    limiter = RateLimiter(2, 60, clock)
    assert limiter.allow("x") and limiter.allow("x")
    assert not limiter.allow("x")
    assert limiter.allow("y")
    clock.now = 61
    assert limiter.allow("x")
