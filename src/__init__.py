"""
Music Source Separator Package
"""

from .separator import MusicSeparator, get_separator, clear_cache, get_best_device
from .metrics import http_requests_total, http_request_duration_seconds, separations_total, separation_duration_seconds, separation_file_size_bytes, errors_total, models_loaded, update_system_metrics, update_temp_storage_metrics, get_metrics, get_metrics_content_type
from .logging_config import setup_logging, get_logger, log_request, log_separation, log_error, log_model_load
from .resilience import retry, CircuitBreaker, RateLimiter, CircuitBreakerOpen, RateLimitExceeded, RetryExhausted

__version__ = "2.0.0"
__all__ = ["MusicSeparator", "get_separator", "clear_cache", "get_best_device",
            "http_requests_total", "http_request_duration_seconds", "separations_total", "separation_duration_seconds", 
                "separation_file_size_bytes", "errors_total", "models_loaded", "update_system_metrics", "update_temp_storage_metrics", 
                "get_metrics", "get_metrics_content_type", 
            "setup_logging", "get_logger", "log_request", "log_separation", "log_error", "log_model_load",
            "retry", "CircuitBreaker", "RateLimiter", "CircuitBreakerOpen", "RateLimitExceeded", "RetryExhausted"]