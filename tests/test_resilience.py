import asyncio

import pytest
import time
from unittest.mock import patch, MagicMock
from src.resilience import (
    retry, CircuitBreaker, RateLimiter, 
    CircuitBreakerOpen, RateLimitExceeded, RetryExhausted, timeout
)


class TestRetry:
    """Test retry functionality"""

    def test_retry_success(self):
        """Test retry with successful function"""
        call_count = 0
        
        @retry(max_attempts=3, delay=0.1)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_eventual_success(self):
        """Test retry with eventual success"""
        call_count = 0
        
        @retry(max_attempts=3, delay=0.1)
        def eventually_successful_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"
        
        result = eventually_successful_func()
        assert result == "success"
        assert call_count == 3

    def test_retry_exhausted(self):
        """Test retry when all attempts exhausted"""
        call_count = 0
        
        @retry(max_attempts=3, delay=0.1)
        def always_failing_func():
            nonlocal call_count
            call_count += 1
            raise Exception("Always failing")
        
        with pytest.raises(RetryExhausted):
            always_failing_func()
        
        assert call_count == 3

    def test_retry_custom_exceptions(self):
        """Test retry with specific exceptions"""
        call_count = 0
        
        @retry(max_attempts=3, delay=0.1, exceptions=(ValueError,))
        def specific_exception_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Specific error")
            return "success"
        
        result = specific_exception_func()
        assert result == "success"
        assert call_count == 2


class TestCircuitBreaker:
    """Test circuit breaker functionality"""

    def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in closed state"""
        cb = CircuitBreaker(failure_threshold=3, timeout=1.0)
        
        @cb.call
        def successful_func():
            return "success"
        
        result = successful_func()
        assert result == "success"
        assert cb.state == "closed"

    def test_circuit_breaker_open_state(self):
        """Test circuit breaker opening after failures"""
        cb = CircuitBreaker(failure_threshold=2, timeout=0.1)
        
        @cb.call
        def failing_func():
            raise Exception("Failure")
        
        # First two failures
        for _ in range(2):
            with pytest.raises(Exception):
                failing_func()
        
        # Third call should raise CircuitBreakerOpen
        with pytest.raises(CircuitBreakerOpen):
            failing_func()
        
        assert cb.state == "open"

    def test_circuit_breaker_half_open_state(self):
        """Test circuit breaker half-open state"""
        cb = CircuitBreaker(failure_threshold=1, timeout=0.1)
        
        @cb.call
        def failing_func():
            raise Exception("Failure")
        
        # Cause circuit to open
        with pytest.raises(Exception):
            failing_func()
        
        # Wait for timeout
        time.sleep(0.2)
        
        # Next call should be in half-open state
        with pytest.raises(Exception):
            failing_func()
        
        # Should still be open
        with pytest.raises(CircuitBreakerOpen):
            failing_func()

    def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery"""
        cb = CircuitBreaker(failure_threshold=1, timeout=0.1)
        
        call_count = 0
        
        @cb.call
        def sometimes_failing_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First failure")
            return "success"
        
        # First call fails and opens circuit
        with pytest.raises(Exception):
            sometimes_failing_func()
        
        # Wait for timeout
        time.sleep(0.2)
        
        # Second call should succeed and close circuit
        result = sometimes_failing_func()
        assert result == "success"
        assert cb.state == "closed"


class TestRateLimiter:
    """Test rate limiter functionality"""

    def test_rate_limiter_allow_request(self):
        """Test rate limiter allowing requests"""
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)
        
        # First 5 requests should be allowed
        for i in range(5):
            assert limiter._allow_request("test_key") is True
        
        # 6th request should be denied
        assert limiter._allow_request("test_key") is False

    def test_rate_limiter_window_expiration(self):
        """Test rate limiter window expiration"""
        limiter = RateLimiter(max_requests=2, window_seconds=0.1)
        
        # First 2 requests allowed
        assert limiter._allow_request("test_key") is True
        assert limiter._allow_request("test_key") is True
        
        # 3rd request denied
        assert limiter._allow_request("test_key") is False
        
        # Wait for window to expire
        time.sleep(0.2)
        
        # Should allow requests again
        assert limiter._allow_request("test_key") is True

    def test_rate_limiter_decorator(self):
        """Test rate limiter decorator"""
        limiter = RateLimiter(max_requests=2, window_seconds=1.0)
        
        @limiter.limit(key="test_user")
        def limited_function():
            return "success"
        
        # First 2 calls should succeed
        assert limited_function() == "success"
        assert limited_function() == "success"
        
        # 3rd call should raise RateLimitExceeded
        with pytest.raises(RateLimitExceeded):
            limited_function()

    def test_rate_limiter_get_remaining(self):
        """Test getting remaining requests"""
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)
        
        # Initially should have all requests remaining
        assert limiter.get_remaining("test_key") == 5
        
        # After one request
        limiter._allow_request("test_key")
        assert limiter.get_remaining("test_key") == 4


class TestTimeout:
    """Test timeout functionality"""

    def test_timeout_sync_function(self):
        """Test timeout with sync function"""
        @timeout(0.1)
        def slow_function():
            time.sleep(0.2)
            return "done"
        
        with pytest.raises(TimeoutError):
            slow_function()

    def test_timeout_sync_success(self):
        """Test timeout with successful sync function"""
        @timeout(1.0)
        def fast_function():
            return "success"
        
        result = fast_function()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_timeout_async_function(self):
        """Test timeout with async function"""
        @timeout(0.1)
        async def slow_async_function():
            await asyncio.sleep(0.2)
            return "done"
        
        with pytest.raises(TimeoutError):
            await slow_async_function()

    @pytest.mark.asyncio
    async def test_timeout_async_success(self):
        """Test timeout with successful async function"""
        @timeout(1.0)
        async def fast_async_function():
            return "success"
        
        result = await fast_async_function()
        assert result == "success"
