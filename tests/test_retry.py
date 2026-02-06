"""Tests for hana.retry module."""

import time

import pytest

from hana.config import RetryConfig
from hana.errors import TransportError
from hana.retry import RetryExhausted, RetryHandler


@pytest.fixture
def retry_config() -> RetryConfig:
    """Create a retry config for testing."""
    return RetryConfig(
        max_attempts=3,
        initial_delay_ms=10,   # Fast for tests
        max_delay_ms=100,
    )


@pytest.fixture
def retry_handler(retry_config: RetryConfig) -> RetryHandler:
    """Create a retry handler for testing."""
    return RetryHandler(retry_config)


class TestRetryHandler:
    """Tests for RetryHandler."""

    def test_success_on_first_try(self, retry_handler: RetryHandler) -> None:
        """Test that successful calls return immediately."""
        call_count = 0

        def success():
            nonlocal call_count
            call_count += 1
            return "success"

        result = retry_handler.execute(success, sku="TEST-001", stage="test")
        assert result == "success"
        assert call_count == 1

    def test_retry_on_transient_error(self, retry_handler: RetryHandler) -> None:
        """Test that retryable errors trigger retries."""
        call_count = 0

        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TransportError(
                    sku="TEST-001",
                    stage="test",
                    message="Temporary failure",
                    retryable=True,
                )
            return "success"

        result = retry_handler.execute(
            fail_then_succeed, sku="TEST-001", stage="test"
        )
        assert result == "success"
        assert call_count == 3

    def test_no_retry_on_non_retryable_error(self, retry_handler: RetryHandler) -> None:
        """Test that non-retryable errors are raised immediately."""
        call_count = 0

        def always_fail():
            nonlocal call_count
            call_count += 1
            raise TransportError(
                sku="TEST-001",
                stage="test",
                message="Permanent failure",
                retryable=False,
            )

        with pytest.raises(TransportError) as exc_info:
            retry_handler.execute(always_fail, sku="TEST-001", stage="test")

        assert exc_info.value.retryable is False
        assert call_count == 1

    def test_retry_exhausted(self, retry_handler: RetryHandler) -> None:
        """Test that RetryExhausted is raised after all attempts."""
        call_count = 0

        def always_fail():
            nonlocal call_count
            call_count += 1
            raise TransportError(
                sku="TEST-001",
                stage="test",
                message="Always fails",
                retryable=True,
            )

        with pytest.raises(RetryExhausted) as exc_info:
            retry_handler.execute(always_fail, sku="TEST-001", stage="test")

        assert exc_info.value.attempts == 3
        assert call_count == 3
        assert isinstance(exc_info.value.last_error, TransportError)

    def test_non_hana_errors_not_retried(self, retry_handler: RetryHandler) -> None:
        """Test that non-HanaError exceptions are raised immediately."""
        call_count = 0

        def raise_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a HanaError")

        with pytest.raises(ValueError):
            retry_handler.execute(raise_value_error, sku="TEST-001", stage="test")

        assert call_count == 1


class TestComputeDelay:
    """Tests for delay computation."""

    def test_exponential_backoff(self, retry_handler: RetryHandler) -> None:
        """Test that delays increase exponentially."""
        # With initial_delay_ms=10, delays should be ~10ms, ~20ms, ~40ms
        # but with jitter, so we check ranges
        d1 = retry_handler.compute_delay(1)
        d2 = retry_handler.compute_delay(2)
        d3 = retry_handler.compute_delay(3)

        # Allow for 25% jitter
        assert 0.0075 <= d1 <= 0.0125  # ~10ms ± 25%
        assert 0.015 <= d2 <= 0.025    # ~20ms ± 25%
        assert 0.030 <= d3 <= 0.050    # ~40ms ± 25%

    def test_max_delay_cap(self) -> None:
        """Test that delay is capped at max_delay_ms."""
        config = RetryConfig(
            max_attempts=10,
            initial_delay_ms=1000,
            max_delay_ms=5000,  # 5 second cap
        )
        handler = RetryHandler(config)

        # After enough attempts, should hit the cap
        delay = handler.compute_delay(10)
        # Max is 5s, with 25% jitter: 3.75s to 6.25s
        assert delay <= 6.25

    def test_jitter_is_random(self, retry_handler: RetryHandler) -> None:
        """Test that jitter adds randomness."""
        delays = [retry_handler.compute_delay(1) for _ in range(100)]
        # With jitter, not all delays should be identical
        unique_delays = set(delays)
        assert len(unique_delays) > 1


class TestIsRetryable:
    """Tests for is_retryable method."""

    def test_retryable_transport_error(self, retry_handler: RetryHandler) -> None:
        """Test that retryable TransportError is detected."""
        error = TransportError(
            sku="TEST",
            stage="test",
            message="test",
            retryable=True,
        )
        assert retry_handler.is_retryable(error) is True

    def test_non_retryable_transport_error(self, retry_handler: RetryHandler) -> None:
        """Test that non-retryable TransportError is detected."""
        error = TransportError(
            sku="TEST",
            stage="test",
            message="test",
            retryable=False,
        )
        assert retry_handler.is_retryable(error) is False

    def test_other_exceptions_not_retryable(self, retry_handler: RetryHandler) -> None:
        """Test that other exceptions are not retryable."""
        assert retry_handler.is_retryable(ValueError("test")) is False
        assert retry_handler.is_retryable(RuntimeError("test")) is False
