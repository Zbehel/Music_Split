"""
Structured Logging Configuration for Music Separator
Uses JSON formatting for easy parsing by log aggregators
"""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict
from typing import Optional, Iterable, MutableMapping


def sanitize_extra(extra: Dict[str, Any], redact_keys: Iterable[str] = ("password", "token", "api_key", "secret")) -> Dict[str, Any]:
    """Sanitize extra dict for logging: redact sensitive keys, truncate long strings and replace binary data."""
    def _sanitize(value, depth=0):
        if depth > 5:
            return str(value)
        if isinstance(value, dict):
            return {
                k: ("[REDACTED]" if any(r in k.lower() for r in redact_keys) else _sanitize(v, depth + 1))
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            seq = [_sanitize(v, depth + 1) for v in value]
            return type(value)(seq) if not isinstance(value, tuple) else tuple(seq)
        if isinstance(value, (bytes, bytearray)):
            return "[binary_data]"
        if isinstance(value, str):
            if len(value) > 200:
                return value[:200] + "...[truncated]"
            return value
        return value

    try:
        return {k: _sanitize(v) for k, v in extra.items()}
    except Exception:
        return {"_sanitization_error": True}
from pathlib import Path
import traceback
import uuid


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs in JSON format
    Compatible with ELK, Loki, CloudWatch, etc.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        
        # Base log structure
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            # Correlation ids (if provided via extra/ContextLogger)
            "request_id": None,
            "trace_id": None,
        }
        
        # Add exception info if present
        if record.exc_info:
            try:
                exc_type = record.exc_info[0]
                exc_name = getattr(exc_type, "__name__", str(exc_type)) if exc_type is not None else None
                exc_msg = str(record.exc_info[1]) if len(record.exc_info) > 1 else None
                exc_tb = traceback.format_exception(*record.exc_info)
            except Exception:
                exc_name = None
                exc_msg = None
                exc_tb = None

            log_data["exception"] = {
                "type": exc_name,
                "message": exc_msg,
                "traceback": exc_tb,
            }
        
        # Add extra fields if present (sanitized)
        record_extra = getattr(record, "extra_data", None)
        if record_extra is not None:
            extra = sanitize_extra(record_extra)
            # Pull request/trace ids to top-level fields if present
            if extra.get("request_id"):
                log_data["request_id"] = extra.pop("request_id")
            if extra.get("trace_id"):
                log_data["trace_id"] = extra.pop("trace_id")
            log_data.update(extra)
        
        # Add custom attributes (set by LoggerAdapter)
        for key in dir(record):
            if key.startswith("_") or key in ["getMessage", "extra_data"]:
                continue
            if key not in ["name", "msg", "args", "created", "filename", "funcName",
                          "levelname", "levelno", "lineno", "module", "msecs",
                          "pathname", "process", "processName", "relativeCreated",
                          "thread", "threadName", "exc_info", "exc_text", "stack_info"]:
                value = getattr(record, key)
                if not callable(value):
                    log_data[key] = value
        
        return json.dumps(log_data, default=str)


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that adds contextual information to logs
    Usage: logger = ContextLogger(base_logger, {"request_id": "123"})
    """
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})
    
    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> tuple:
        """Add context to log message"""
        # Merge extra data
        extra_data = dict(self.extra or {})
        if "extra" in kwargs:
            extra_data.update(kwargs["extra"])
            del kwargs["extra"]
        
        # Add extra_data to record
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        kwargs["extra"]["extra_data"] = extra_data
        
        return msg, kwargs


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = True
) -> logging.Logger:
    """
    Setup structured logging
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for logs
        json_format: Use JSON formatting (True) or plain text (False)
    
    Returns:
        Configured root logger
    """
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Create formatter
    if json_format:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    return root_logger


def get_logger(name: str, context: Optional[Dict[str, Any]] = None) -> logging.Logger | logging.LoggerAdapter:
    """
    Get a logger with optional context
    
    Args:
        name: Logger name (usually __name__)
        context: Optional context to add to all logs
    
    Returns:
        Logger or ContextLogger
    """
    base_logger = logging.getLogger(name)
    
    if context:
        return ContextLogger(base_logger, context)
    
    return base_logger


# ============================================================
# CONVENIENCE LOGGING FUNCTIONS
# ============================================================

def log_request(
    logger: logging.Logger | logging.LoggerAdapter,
    method: str,
    endpoint: str,
    status: int,
    duration: float,
    **extra
):
    """Log HTTP request with structured data"""
    logger.info(
        f"{method} {endpoint} - {status}",
        extra={
            "extra_data": {
                "event_type": "http_request",
                "method": method,
                "endpoint": endpoint,
                "status_code": status,
                "duration_seconds": duration,
                **extra
            }
        }
    )


def log_separation(
    logger: logging.Logger | logging.LoggerAdapter,
    model: str,
    audio_duration: float,
    processing_duration: float,
    status: str,
    **extra
):
    """Log audio separation with structured data"""
    logger.info(
        f"Separation completed: {model}",
        extra={
            "extra_data": {
                "event_type": "audio_separation",
                "model": model,
                "audio_duration_seconds": audio_duration,
                "processing_duration_seconds": processing_duration,
                "status": status,
                **extra
            }
        }
    )


def log_error(
    logger: logging.Logger | logging.LoggerAdapter,
    error: Exception,
    context: Optional[str] = None,
    **extra
):
    """Log error with structured data"""
    logger.error(
        f"Error: {str(error)}",
        extra={
            "extra_data": {
                "event_type": "error",
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context,
                **extra
            }
        },
        exc_info=True
    )


def log_model_load(
    logger: logging.Logger | logging.LoggerAdapter,
    model: str,
    duration: float,
    device: str,
    success: bool = True,
    **extra
):
    """Log model loading with structured data"""
    logger.info(
        f"Model loaded: {model}",
        extra={
            "extra_data": {
                "event_type": "model_load",
                "model": model,
                "duration_seconds": duration,
                "device": device,
                "success": success,
                **extra
            }
        }
    )


def log_system_metrics(
    logger: logging.Logger | logging.LoggerAdapter,
    cpu_percent: float,
    memory_percent: float,
    disk_percent: float,
    **extra
):
    """Log system metrics with structured data"""
    logger.debug(
        "System metrics",
        extra={
            "extra_data": {
                "event_type": "system_metrics",
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "disk_percent": disk_percent,
                **extra
            }
        }
    )


# ============================================================
# LOG LEVELS HELPERS
# ============================================================

def set_log_level(level: str):
    """Set log level for all loggers"""
    logging.getLogger().setLevel(getattr(logging, level.upper()))


def enable_debug():
    """Enable debug logging"""
    set_log_level("DEBUG")


def enable_info():
    """Enable info logging"""
    set_log_level("INFO")


# ============================================================
# EXAMPLE USAGE
# ============================================================

if __name__ == "__main__":
    # Setup logging
    setup_logging(level="INFO", json_format=True)
    
    # Get logger
    logger = get_logger(__name__)
    
    # Example logs
    logger.info("Application started")
    
    # With context
    request_logger = get_logger(__name__, {"request_id": "abc-123"})
    request_logger.info("Processing request")
    
    # Structured logging
    log_request(logger, "POST", "/separate", 200, 1.5, user_id="user-123")
    
    # Error logging
    try:
        raise ValueError("Something went wrong")
    except Exception as e:
        log_error(logger, e, context="test_operation")