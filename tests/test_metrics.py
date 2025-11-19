# tests/test_metrics.py
import pytest
from unittest.mock import patch

from src.metrics import (
    http_requests_total, http_request_duration_seconds, separations_total,
    separation_duration_seconds, separation_file_size_bytes, errors_total,
    models_loaded, update_system_metrics, update_temp_storage_metrics,
    get_metrics, get_metrics_content_type
)


class TestMetrics:
    """Test Prometheus metrics"""

    def test_metric_initialization(self):
        """Test that metrics are properly initialized"""
        assert http_requests_total is not None
        assert http_request_duration_seconds is not None
        assert separations_total is not None
        assert separation_duration_seconds is not None
        assert separation_file_size_bytes is not None
        assert errors_total is not None
        assert models_loaded is not None

    def test_metric_labels(self):
        """Test that metrics accept expected labels"""
        # Test http_requests_total
        http_requests_total.labels(method="GET", endpoint="/test", status=200).inc()
        
        # Test separations_total
        separations_total.labels(model="htdemucs", status="success").inc()
        
        # Test errors_total
        errors_total.labels(type="TestError", endpoint="/test").inc()

    def test_update_system_metrics(self):
        """Test updating system metrics"""
        with patch('psutil.cpu_percent') as mock_cpu, \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.disk_usage') as mock_disk:
            
            mock_cpu.return_value = 50.0
            mock_memory.return_value.percent = 60.0
            mock_disk.return_value.percent = 40.0
            
            update_system_metrics()
            
            # Verify mocks were called
            mock_cpu.assert_called_once()
            mock_memory.assert_called_once()
            mock_disk.assert_called_once()

    def test_update_temp_storage_metrics(self, tmp_path):
        """Test updating temp storage metrics"""
        # Create some test files
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content" * 100)  # ~1.2KB
        
        update_temp_storage_metrics(str(tmp_path))
        
        # Verify metrics were updated (this would require accessing the gauge value)

    def test_get_metrics(self):
        """Test getting metrics text"""
        metrics_text = get_metrics()
        # Handle both string and bytes return types
        if isinstance(metrics_text, bytes):
            metrics_text = metrics_text.decode('utf-8')
        assert isinstance(metrics_text, str)
        assert len(metrics_text) > 0

    def test_get_metrics_content_type(self):
        """Test getting metrics content type"""
        content_type = get_metrics_content_type()
        assert content_type == "text/plain; version=0.0.4; charset=utf-8"
