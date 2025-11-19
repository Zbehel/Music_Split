"""
Structured Logging Configuration for Music Separator
Uses JSON formatting for easy parsing by log aggregators
"""

import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict
from pathlib import Path
import traceback


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs in JSON format
    Compatible with ELK, Loki, CloudWatch, etc.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        
        # Base log structure
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": [str(tb) for tb in traceback.format_exception(*record.exc_info)]
            }
        
        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)
        
        return json.dumps(log_data, default=str)


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that adds contextual information to logs
    Usage: logger = ContextLogger(base_logger, {"request_id": "123"})
    """
    
    def __init__(self, logger: logging.Logger, extra: Dict[str, Any] = None):
        super().__init__(logger, extra or {})
    
    def process(self, msg: str, kwargs: dict) -> tuple:
        """Add context to log message"""
        # Merge extra data
        extra_data = {**self.extra}
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
    log_file: str = None,
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


def get_logger(name: str, context: Dict[str, Any] = None) -> logging.Logger:
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


def log_request(
    logger: logging.Logger,
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
    logger: logging.Logger,
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
    logger: logging.Logger,
    error: Exception,
    context: str = None,
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
    logger: logging.Logger,
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