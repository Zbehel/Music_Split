"""
Prometheus Metrics for Music Separator API
Tracks requests, errors, processing times, and resource usage
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from functools import wraps
import time
import psutil
import torch
from typing import Callable
import logging

logger = logging.getLogger(__name__)

# ============================================================
# REQUEST METRICS
# ============================================================

# HTTP Requests
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

# ============================================================
# SEPARATION METRICS
# ============================================================

separations_total = Counter(
    'separations_total',
    'Total audio separations',
    ['model', 'status']
)

separation_duration_seconds = Histogram(
    'separation_duration_seconds',
    'Audio separation duration in seconds',
    ['model'],
    buckets=[5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1200.0]
)

separation_audio_duration_seconds = Histogram(
    'separation_audio_duration_seconds',
    'Duration of input audio being processed',
    buckets=[10.0, 30.0, 60.0, 120.0, 180.0, 300.0, 600.0]
)

separation_file_size_bytes = Histogram(
    'separation_file_size_bytes',
    'Size of uploaded audio files',
    buckets=[1e6, 5e6, 10e6, 25e6, 50e6, 100e6, 200e6]
)

# ============================================================
# MODEL METRICS
# ============================================================

model_load_duration_seconds = Histogram(
    'model_load_duration_seconds',
    'Model loading duration in seconds',
    ['model'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0]
)

models_loaded = Gauge(
    'models_loaded',
    'Number of models currently loaded in memory',
    ['model']
)

model_inference_duration_seconds = Histogram(
    'model_inference_duration_seconds',
    'Model inference duration in seconds',
    ['model'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

# ============================================================
# ERROR METRICS
# ============================================================

errors_total = Counter(
    'errors_total',
    'Total errors',
    ['type', 'endpoint']
)

# ============================================================
# SYSTEM METRICS
# ============================================================

# CPU
cpu_usage_percent = Gauge(
    'cpu_usage_percent',
    'CPU usage percentage'
)

# Memory
memory_usage_bytes = Gauge(
    'memory_usage_bytes',
    'Memory usage in bytes'
)

memory_available_bytes = Gauge(
    'memory_available_bytes',
    'Available memory in bytes'
)

memory_percent = Gauge(
    'memory_percent',
    'Memory usage percentage'
)

# GPU (if available)
gpu_memory_used_bytes = Gauge(
    'gpu_memory_used_bytes',
    'GPU memory used in bytes',
    ['device']
)

gpu_memory_total_bytes = Gauge(
    'gpu_memory_total_bytes',
    'GPU memory total in bytes',
    ['device']
)

gpu_utilization_percent = Gauge(
    'gpu_utilization_percent',
    'GPU utilization percentage',
    ['device']
)

# Disk
disk_usage_bytes = Gauge(
    'disk_usage_bytes',
    'Disk usage in bytes',
    ['path']
)

disk_free_bytes = Gauge(
    'disk_free_bytes',
    'Disk free space in bytes',
    ['path']
)

# ============================================================
# SESSION METRICS
# ============================================================

active_sessions = Gauge(
    'active_sessions',
    'Number of active separation sessions'
)

temp_files_total = Gauge(
    'temp_files_total',
    'Total number of temporary files'
)

temp_storage_bytes = Gauge(
    'temp_storage_bytes',
    'Total size of temporary storage in bytes'
)

# ============================================================
# DECORATORS
# ============================================================

def track_request(endpoint: str):
    """Decorator to track HTTP requests"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                errors_total.labels(
                    type=type(e).__name__,
                    endpoint=endpoint
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                http_requests_total.labels(
                    method="POST",
                    endpoint=endpoint,
                    status=status
                ).inc()
                http_request_duration_seconds.labels(
                    method="POST",
                    endpoint=endpoint
                ).observe(duration)
        
        return wrapper
    return decorator


def track_separation(model: str):
    """Decorator to track audio separation"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                errors_total.labels(
                    type=type(e).__name__,
                    endpoint="separation"
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                separations_total.labels(
                    model=model,
                    status=status
                ).inc()
                separation_duration_seconds.labels(
                    model=model
                ).observe(duration)
        
        return wrapper
    return decorator


# ============================================================
# SYSTEM METRICS COLLECTOR
# ============================================================

def update_system_metrics():
    """Update system metrics (CPU, memory, disk, GPU)"""
    try:
        # CPU
        cpu_usage_percent.set(psutil.cpu_percent(interval=0.1))
        
        # Memory
        mem = psutil.virtual_memory()
        memory_usage_bytes.set(mem.used)
        memory_available_bytes.set(mem.available)
        memory_percent.set(mem.percent)
        
        # Disk (for temp directory)
        disk = psutil.disk_usage('/tmp')
        disk_usage_bytes.labels(path='/tmp').set(disk.used)
        disk_free_bytes.labels(path='/tmp').set(disk.free)
        
        # GPU (if CUDA available)
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                try:
                    mem_used = torch.cuda.memory_allocated(i)
                    mem_total = torch.cuda.get_device_properties(i).total_memory
                    
                    gpu_memory_used_bytes.labels(device=f'cuda:{i}').set(mem_used)
                    gpu_memory_total_bytes.labels(device=f'cuda:{i}').set(mem_total)
                    
                    # Utilization (approximation based on memory)
                    util = (mem_used / mem_total) * 100 if mem_total > 0 else 0
                    gpu_utilization_percent.labels(device=f'cuda:{i}').set(util)
                except Exception as e:
                    logger.warning(f"Could not collect GPU metrics for device {i}: {e}")
    
    except Exception as e:
        logger.error(f"Error updating system metrics: {e}")


# ============================================================
# TEMP STORAGE METRICS
# ============================================================

def update_temp_storage_metrics(temp_dir: str):
    """Update metrics for temporary storage"""
    try:
        from pathlib import Path
        temp_path = Path(temp_dir)
        
        if not temp_path.exists():
            return
        
        # Count sessions
        sessions = [d for d in temp_path.iterdir() if d.is_dir()]
        active_sessions.set(len(sessions))
        
        # Count files and calculate total size
        total_files = 0
        total_size = 0
        
        for session_dir in sessions:
            for file in session_dir.rglob('*'):
                if file.is_file():
                    total_files += 1
                    total_size += file.stat().st_size
        
        temp_files_total.set(total_files)
        temp_storage_bytes.set(total_size)
    
    except Exception as e:
        logger.error(f"Error updating temp storage metrics: {e}")


# ============================================================
# METRICS ENDPOINT
# ============================================================

def get_metrics():
    """Generate metrics for Prometheus scraping"""
    return generate_latest()


def get_metrics_content_type():
    """Get content type for metrics endpoint"""
    return CONTENT_TYPE_LATEST