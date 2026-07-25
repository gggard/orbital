"""Unit tests for the in-process sliding-window limiter (orbital.ratelimit)."""

from orbital.ratelimit import RateLimiter


def test_under_limit_passes():
    rl = RateLimiter()
    for _ in range(5):
        assert rl.check("k", limit=5, window_seconds=60) is True


def test_over_limit_blocks():
    rl = RateLimiter()
    for _ in range(5):
        assert rl.check("k", limit=5, window_seconds=60) is True
    assert rl.check("k", limit=5, window_seconds=60) is False
    # still blocked, doesn't "use up" further budget
    assert rl.check("k", limit=5, window_seconds=60) is False


def test_different_keys_do_not_interfere():
    rl = RateLimiter()
    for _ in range(5):
        assert rl.check("ip-a", limit=5, window_seconds=60) is True
    assert rl.check("ip-a", limit=5, window_seconds=60) is False
    # a different key has its own independent budget
    assert rl.check("ip-b", limit=5, window_seconds=60) is True


def test_window_expiry_frees_up_budget(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("orbital.ratelimit.time.monotonic", lambda: now[0])

    rl = RateLimiter()
    for _ in range(3):
        assert rl.check("k", limit=3, window_seconds=10) is True
    assert rl.check("k", limit=3, window_seconds=10) is False

    # advance past the window: old hits age out, budget is available again
    now[0] += 10.001
    assert rl.check("k", limit=3, window_seconds=10) is True


def test_reset_clears_state():
    rl = RateLimiter()
    for _ in range(5):
        assert rl.check("k", limit=5, window_seconds=60) is True
    assert rl.check("k", limit=5, window_seconds=60) is False

    rl.reset()
    assert rl.check("k", limit=5, window_seconds=60) is True


def test_evicts_stale_keys_when_at_capacity(monkeypatch):
    monkeypatch.setattr("orbital.ratelimit.MAX_TRACKED_KEYS", 2)
    now = [0.0]
    monkeypatch.setattr("orbital.ratelimit.time.monotonic", lambda: now[0])

    rl = RateLimiter()
    rl.check("a", limit=5, window_seconds=1)
    rl.check("b", limit=5, window_seconds=1)
    assert set(rl._hits) == {"a", "b"}

    now[0] += 2  # both "a" and "b" are now stale relative to the 1s window
    # inserting a third key at capacity should evict the stale ones first,
    # rather than growing the store past MAX_TRACKED_KEYS
    rl.check("c", limit=5, window_seconds=1)
    assert "a" not in rl._hits
    assert "b" not in rl._hits
    assert "c" in rl._hits
    assert len(rl._hits) <= 2
