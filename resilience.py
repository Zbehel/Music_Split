"""
Resilience Patterns for Music Separator
Implements retry logic, circuit breaker, and rate limiting
"""

import asyncio
import time
from typing import Callable, Any, Optional, Dict
from functools import wraps
from collections import defaultdict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# ============================================================
# RETRY LOGIC
# ============================================================

class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted"""
    pass


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Retry decorator with exponential backoff
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback called on each retry
    
    Example:
        @retry(max_attempts=3, delay=1.0, backoff=2.0)
        def flaky_operation():
            # might fail occasionally
            pass
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    
                    if attempt >= max_attempts:
                        logger.error(
                            f"Retry exhausted for {func.__name__} after {max_attempts} attempts",
                            extra={"function": func.__name__, "attempts": attempt}
                        )
                        raise RetryExhausted(
                            f"Failed after {max_attempts} attempts: {str(e)}"
                        ) from e
                    
                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "delay": current_delay,
                            "error": str(e)
                        }
                    )
                    
                    if on_retry:
                        on_retry(attempt, e)
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
        
        return wrapper
    return decorator


async def async_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Async retry decorator with exponential backoff
    
    Example:
        @async_retry(max_attempts=3, delay=1.0)
        async def flaky_async_operation():
            # might fail occasionally
            pass
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            
            while attempt < max_attempts:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    
                    if attempt >= max_attempts:
                        logger.error(
                            f"Async retry exhausted for {func.__name__}",
                            extra={"function": func.__name__, "attempts": attempt}
                        )
                        raise RetryExhausted(
                            f"Failed after {max_attempts} attempts: {str(e)}"
                        ) from e
                    
                    logger.warning(
                        f"Async retry {attempt}/{max_attempts} for {func.__name__}",
                        extra={"function": func.__name__, "attempt": attempt}
                    )
                    
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
        
        return wrapper
    return decorator


# ============================================================
# CIRCUIT BREAKER
# ============================================================

class CircuitBreakerState:
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """
    Circuit breaker pattern implementation
    
    Prevents cascading failures by stopping requests to a failing service
    
    States:
        - CLOSED: Normal operation, requests pass through
        - OPEN: Too many failures, reject all requests
        - HALF_OPEN: Testing if service recovered
    
    Example:
        cb = CircuitBreaker(failure_threshold=5, timeout=60)
        
        @cb.call
        def external_api_call():
            # might fail
            pass
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        """
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting recovery (HALF_OPEN)
            expected_exception: Exception type that counts as failure
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
    
    def call(self, func: Callable):
        """Decorator to wrap function with circuit breaker"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info(
                        f"Circuit breaker HALF_OPEN for {func.__name__}",
                        extra={"function": func.__name__, "state": self.state}
                    )
                else:
                    logger.warning(
                        f"Circuit breaker OPEN for {func.__name__}",
                        extra={"function": func.__name__, "state": self.state}
                    )
                    raise CircuitBreakerOpen(
                        f"Circuit breaker is OPEN for {func.__name__}"
                    )
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise
        
        return wrapper
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time >= self.timeout
    
    def _on_success(self):
        """Handle successful call"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            logger.info("Circuit breaker recovered, closing")
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            logger.warning("Circuit breaker test failed, reopening")
            self.state = CircuitBreakerState.OPEN
        elif self.failure_count >= self.failure_threshold:
            logger.error(
                f"Circuit breaker threshold reached ({self.failure_count} failures), opening",
                extra={"failure_count": self.failure_count, "threshold": self.failure_threshold}
            )
            self.state = CircuitBreakerState.OPEN
    
    def reset(self):
        """Manually reset circuit breaker"""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        logger.info("Circuit breaker manually reset")


# ============================================================
# RATE LIMITING
# ============================================================

class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded"""
    pass


class RateLimiter:
    """
    Token bucket rate limiter
    
    Limits the rate of operations per time window
    
    Example:
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        
        @limiter.limit
        def api_call():
            # limited to 10 calls per minute
            pass
    """
    
    def __init__(self, max_requests: int, window_seconds: float):
        """
        Args:
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = defaultdict(list)
    
    def limit(self, key: str = "default"):
        """
        Decorator to apply rate limiting
        
        Args:
            key: Identifier for separate rate limits (e.g., user_id, ip_address)
        """
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not self._allow_request(key):
                    logger.warning(
                        f"Rate limit exceeded for {func.__name__}",
                        extra={"function": func.__name__, "key": key}
                    )
                    raise RateLimitExceeded(
                        f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds}s"
                    )
                
                return func(*args, **kwargs)
            
            return wrapper
        return decorator
    
    def _allow_request(self, key: str) -> bool:
        """Check if request is allowed under rate limit"""
        now = time.time()
        
        # Clean old requests outside window
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if now - req_time < self.window_seconds
        ]
        
        # Check if under limit
        if len(self.requests[key]) >= self.max_requests:
            return False
        
        # Add current request
        self.requests[key].append(now)
        return True
    
    def get_remaining(self, key: str = "default") -> int:
        """Get remaining requests for key"""
        now = time.time()
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if now - req_time < self.window_seconds
        ]
        return max(0, self.max_requests - len(self.requests[key]))
    
    def reset(self, key: str = "default"):
        """Reset rate limit for key"""
        self.requests[key] = []


# ============================================================
# TIMEOUT DECORATOR
# ============================================================

class TimeoutError(Exception):
    """Raised when operation times out"""
    pass


def timeout(seconds: float):
    """
    Timeout decorator for functions
    
    Args:
        seconds: Maximum execution time
    
    Example:
        @timeout(30.0)
        def long_running_operation():
            # will raise TimeoutError after 30 seconds
            pass
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=seconds
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"Timeout after {seconds}s for {func.__name__}",
                    extra={"function": func.__name__, "timeout": seconds}
                )
                raise TimeoutError(
                    f"Operation {func.__name__} timed out after {seconds}s"
                )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            import signal
            
            def handler(signum, frame):
                raise TimeoutError(
                    f"Operation {func.__name__} timed out after {seconds}s"
                )
            
            # Set alarm
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(int(seconds))
            
            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # Cancel alarm
                return result
            except TimeoutError:
                logger.error(
                    f"Timeout after {seconds}s for {func.__name__}",
                    extra={"function": func.__name__, "timeout": seconds}
                )
                raise
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# ============================================================
# EXAMPLE USAGE
# ============================================================

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Retry example
    @retry(max_attempts=3, delay=1.0, backoff=2.0)
    def flaky_function():
        import random
        if random.random() < 0.7:
            raise Exception("Random failure")
        return "Success"
    
    # Circuit breaker example
    cb = CircuitBreaker(failure_threshold=3, timeout=5.0)
    
    @cb.call
    def external_service():
        import random
        if random.random() < 0.8:
            raise Exception("Service unavailable")
        return "OK"
    
    # Rate limiter example
    limiter = RateLimiter(max_requests=5, window_seconds=10)
    
    @limiter.limit(key="user-123")
    def api_endpoint():
        return "Response"
    
    print("Testing resilience patterns...")
    
    # Test retry
    try:
        result = flaky_function()
        print(f"Retry test: {result}")
    except RetryExhausted as e:
        print(f"Retry test failed: {e}")
    
    # Test circuit breaker
    for i in range(10):
        try:
            result = external_service()
            print(f"Circuit breaker test {i}: {result}")
        except (CircuitBreakerOpen, Exception) as e:
            print(f"Circuit breaker test {i}: {type(e).__name__}")
        time.sleep(0.5)
    
    # Test rate limiter
    for i in range(8):
        try:
            result = api_endpoint()
            remaining = limiter.get_remaining("user-123")
            print(f"Rate limiter test {i}: {result}, {remaining} remaining")
        except RateLimitExceeded as e:
            print(f"Rate limiter test {i}: {e}")