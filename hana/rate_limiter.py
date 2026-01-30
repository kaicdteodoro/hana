"""
hana.rate_limiter — Rate limiting and backpressure control.

Token bucket rate limiter with backpressure detection.
"""

import threading
import time
from collections import deque
from typing import Callable

from hana.config import (
    BackpressureConfig,
    BackpressureStrategy,
    BackpressureTrigger,
    HanaConfig,
    RateLimitConfig,
)
from hana.logger import get_logger


class TokenBucketRateLimiter:
    """Token bucket rate limiter for HTTP requests."""

    def __init__(self, requests_per_second: int, burst: int):
        self._rate = requests_per_second
        self._burst = burst
        self._tokens = float(burst)
        self._last_update = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Acquire a token, blocking if necessary."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_update = now

            if self._tokens >= 1:
                self._tokens -= 1
                return

            wait_time = (1 - self._tokens) / self._rate
            self._tokens = 0

        time.sleep(wait_time)

    def try_acquire(self) -> bool:
        """Try to acquire a token without blocking."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_update = now

            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False


class BackpressureMonitor:
    """Monitor for detecting backpressure conditions."""

    def __init__(self, config: BackpressureConfig):
        self._config = config
        self._consecutive_errors = 0
        self._error_history: deque[tuple[float, bool]] = deque(maxlen=100)
        self._response_times: deque[float] = deque(maxlen=100)
        self._lock = threading.Lock()
        self._triggered = False
        self._cooldown_until: float = 0

    def record_success(self, response_time_ms: float) -> None:
        """Record a successful operation."""
        with self._lock:
            self._consecutive_errors = 0
            self._error_history.append((time.monotonic(), False))
            self._response_times.append(response_time_ms)

    def record_error(self) -> None:
        """Record a failed operation."""
        with self._lock:
            self._consecutive_errors += 1
            self._error_history.append((time.monotonic(), True))

    def is_triggered(self) -> bool:
        """Check if backpressure is triggered."""
        with self._lock:
            if time.monotonic() < self._cooldown_until:
                return True

            if self._config.trigger == BackpressureTrigger.CONSECUTIVE_ERRORS:
                return self._consecutive_errors >= self._config.threshold

            elif self._config.trigger == BackpressureTrigger.ERROR_RATE:
                if len(self._error_history) < 10:
                    return False
                now = time.monotonic()
                window = 60.0
                recent = [
                    is_error
                    for ts, is_error in self._error_history
                    if now - ts < window
                ]
                if not recent:
                    return False
                error_rate = sum(recent) / len(recent) * 100
                return error_rate >= self._config.threshold

            elif self._config.trigger == BackpressureTrigger.RESPONSE_TIME:
                if len(self._response_times) < 10:
                    return False
                avg_response = sum(self._response_times) / len(self._response_times)
                return avg_response >= self._config.threshold

            return False

    def start_cooldown(self) -> None:
        """Start the cooldown period."""
        with self._lock:
            self._cooldown_until = time.monotonic() + self._config.cooldown_seconds
            self._consecutive_errors = 0

    def reset(self) -> None:
        """Reset the monitor state."""
        with self._lock:
            self._consecutive_errors = 0
            self._error_history.clear()
            self._response_times.clear()
            self._triggered = False
            self._cooldown_until = 0

    @property
    def strategy(self) -> BackpressureStrategy:
        return self._config.strategy

    @property
    def cooldown_seconds(self) -> int:
        return self._config.cooldown_seconds


class RateLimitedExecutor:
    """Executor that applies rate limiting and backpressure."""

    def __init__(self, config: HanaConfig):
        self._rate_limiter = TokenBucketRateLimiter(
            config.rate_limit.requests_per_second,
            config.rate_limit.burst,
        )
        self._backpressure = BackpressureMonitor(config.backpressure)
        self._logger = get_logger()

    def execute(
        self,
        func: Callable,
        sku: str | None = None,
    ) -> tuple[bool, any]:
        """
        Execute a function with rate limiting.

        Returns:
            Tuple of (success, result_or_exception)
        """
        if self._backpressure.is_triggered():
            if self._backpressure.strategy == BackpressureStrategy.PAUSE:
                self._logger.warn(
                    f"Backpressure triggered, pausing for {self._backpressure.cooldown_seconds}s",
                    sku=sku,
                    stage="backpressure",
                )
                time.sleep(self._backpressure.cooldown_seconds)
                self._backpressure.reset()
            elif self._backpressure.strategy == BackpressureStrategy.SKIP:
                return (False, "backpressure")
            elif self._backpressure.strategy == BackpressureStrategy.ABORT:
                raise RuntimeError("Backpressure abort triggered")

        self._rate_limiter.acquire()

        start = time.monotonic()
        try:
            result = func()
            elapsed_ms = (time.monotonic() - start) * 1000
            self._backpressure.record_success(elapsed_ms)
            return (True, result)
        except Exception as e:
            self._backpressure.record_error()
            return (False, e)

    @property
    def backpressure(self) -> BackpressureMonitor:
        return self._backpressure
