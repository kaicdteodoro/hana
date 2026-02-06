"""
hana.retry — Retry logic with exponential backoff.

Handles transient failures with configurable retry strategies.
"""

import random
import time
from functools import wraps
from typing import Any, Callable, TypeVar

from hana.config import RetryConfig
from hana.errors import HanaError, TransportError
from hana.logger import get_logger

T = TypeVar("T")


class RetryExhausted(HanaError):
    """All retry attempts exhausted."""

    def __init__(
        self,
        sku: str,
        stage: str,
        message: str,
        attempts: int,
        last_error: Exception,
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(
            sku=sku,
            stage=stage,
            message=message,
            payload={
                **(payload or {}),
                "attempts": attempts,
                "last_error_type": type(last_error).__name__,
                "last_error_message": str(last_error),
            },
        )
        self.attempts = attempts
        self.last_error = last_error


class RetryHandler:
    """Handles retry logic with exponential backoff and jitter."""

    def __init__(self, config: RetryConfig):
        self._config = config
        self._logger = get_logger()

    def compute_delay(self, attempt: int) -> float:
        """
        Compute delay for a given attempt using exponential backoff with jitter.

        Args:
            attempt: Current attempt number (1-indexed)

        Returns:
            Delay in seconds
        """
        base_delay_s = self._config.initial_delay_ms / 1000.0
        max_delay_s = self._config.max_delay_ms / 1000.0

        # Exponential backoff: delay = base * 2^(attempt-1)
        exponential_delay = base_delay_s * (2 ** (attempt - 1))

        # Cap at max delay
        capped_delay = min(exponential_delay, max_delay_s)

        # Add jitter (±25%)
        jitter = capped_delay * 0.25 * (2 * random.random() - 1)
        final_delay = capped_delay + jitter

        return max(0, final_delay)

    def is_retryable(self, error: Exception) -> bool:
        """Check if an error is retryable."""
        if isinstance(error, TransportError):
            return error.retryable
        return False

    def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        sku: str = "",
        stage: str = "retry",
        **kwargs: Any,
    ) -> T:
        """
        Execute a function with retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            sku: SKU for logging/error context
            stage: Stage for logging/error context
            **kwargs: Keyword arguments for func

        Returns:
            Result of func

        Raises:
            RetryExhausted: If all retries are exhausted
            Exception: If error is not retryable
        """
        last_error: Exception | None = None

        for attempt in range(1, self._config.max_attempts + 1):
            try:
                return func(*args, **kwargs)

            except Exception as e:
                last_error = e

                if not self.is_retryable(e):
                    # Not retryable, raise immediately
                    raise

                if attempt >= self._config.max_attempts:
                    # Last attempt, will raise RetryExhausted below
                    break

                delay = self.compute_delay(attempt)
                self._logger.warn(
                    f"Attempt {attempt}/{self._config.max_attempts} failed, "
                    f"retrying in {delay:.2f}s: {e}",
                    sku=sku,
                    stage=stage,
                    data={
                        "attempt": attempt,
                        "delay_s": delay,
                        "error_type": type(e).__name__,
                    },
                )
                time.sleep(delay)

        raise RetryExhausted(
            sku=sku,
            stage=stage,
            message=f"All {self._config.max_attempts} retry attempts exhausted",
            attempts=self._config.max_attempts,
            last_error=last_error,
        )


def with_retry(
    config: RetryConfig,
    sku: str = "",
    stage: str = "retry",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator factory for adding retry logic to functions.

    Usage:
        @with_retry(config.retry, sku="SKU-001", stage="media_upload")
        def upload_file():
            ...
    """
    handler = RetryHandler(config)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return handler.execute(func, *args, sku=sku, stage=stage, **kwargs)

        return wrapper

    return decorator
