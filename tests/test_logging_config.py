# test_logging_config.py
import pytest
import json
import logging
from src.logging_config import (
    StructuredFormatter, ContextLogger, setup_logging, get_logger,
    log_request, log_separation, log_error, log_model_load
)


class TestStructuredFormatter:
    """Test structured formatter"""

    def test_format_record(self):
        """Test formatting log record as JSON"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert "timestamp" in parsed

    def test_format_with_exception(self):
        """Test formatting with exception info"""
        formatter = StructuredFormatter()
        try:
            raise ValueError("Test error")
        except ValueError as e:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="Error occurred",
                args=(),
                exc_info=(type(e), e, e.__traceback__)
            )
            
            formatted = formatter.format(record)
            parsed = json.loads(formatted)
            
            assert "exception" in parsed
            assert parsed["exception"]["type"] == "ValueError"


class TestContextLogger:
    """Test context logger"""

    def test_context_logger_creation(self):
        """Test creating context logger"""
        base_logger = logging.getLogger("test")
        context_logger = ContextLogger(base_logger, {"request_id": "123"})
        assert isinstance(context_logger, ContextLogger)

    def test_context_logger_process(self):
        """Test processing with context"""
        base_logger = logging.getLogger("test")
        context_logger = ContextLogger(base_logger, {"request_id": "123"})
        
        msg, kwargs = context_logger.process("Test message", {})
        assert msg == "Test message"
        assert "extra" in kwargs
        assert "extra_data" in kwargs["extra"]
        assert kwargs["extra"]["extra_data"]["request_id"] == "123"


class TestLoggingSetup:
    """Test logging setup"""

    def test_setup_logging_json(self):
        """Test setup with JSON formatting"""
        logger = setup_logging(level="INFO", json_format=True)
        assert logger.level == logging.INFO

    def test_setup_logging_plain(self):
        """Test setup with plain text formatting"""
        logger = setup_logging(level="INFO", json_format=False)
        assert logger.level == logging.INFO

    def test_get_logger(self):
        """Test getting logger"""
        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_with_context(self):
        """Test getting logger with context"""
        logger = get_logger("test", {"context": "test"})
        assert isinstance(logger, ContextLogger)


class TestStructuredLogging:
    """Test structured logging functions"""

    def test_log_request(self, caplog):
        """Test logging HTTP request"""
        logger = get_logger("test")
        with caplog.at_level(logging.INFO):
            log_request(logger, "GET", "/test", 200, 0.5, user_id="user123")
            
            # Check that log was recorded
            assert len(caplog.records) > 0
            record = caplog.records[0]
            assert "GET /test - 200" in record.getMessage()

    def test_log_separation(self, caplog):
        """Test logging audio separation"""
        logger = get_logger("test")
        with caplog.at_level(logging.INFO):
            log_separation(logger, "htdemucs", 30.0, 10.0, "success", session_id="sess123")
            
            assert len(caplog.records) > 0
            record = caplog.records[0]
            assert "Separation completed" in record.getMessage()

    def test_log_error(self, caplog):
        """Test logging error"""
        logger = get_logger("test")
        with caplog.at_level(logging.ERROR):
            try:
                raise ValueError("Test error")
            except ValueError as e:
                log_error(logger, e, context="test_operation")
            
            assert len(caplog.records) > 0
            record = caplog.records[0]
            assert "Error:" in record.getMessage()

    def test_log_model_load(self, caplog):
        """Test logging model load"""
        logger = get_logger("test")
        with caplog.at_level(logging.INFO):
            log_model_load(logger, "htdemucs", 2.5, "cuda", success=True)
            
            assert len(caplog.records) > 0
            record = caplog.records[0]
            assert "Model loaded" in record.getMessage()