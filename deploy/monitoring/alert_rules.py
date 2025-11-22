# Prometheus Alert Rules for Music Separator

groups:
  # ============================================================
  # API HEALTH ALERTS
  # ============================================================
  - name: api_health
    interval: 30s
    rules:
      - alert: APIDown
        expr: up{job="music-separator-api"} == 0
        for: 1m
        labels:
          severity: critical
          component: api
        annotations:
          summary: "Music Separator API is down"
          description: "The API has been down for more than 1 minute"

      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status="500"}[5m]) /
          rate(http_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
          component: api
        annotations:
          summary: "High error rate detected"
          description: "Error rate is above 5% for the last 5 minutes (current: {{ $value | humanizePercentage }})"

      - alert: VeryHighErrorRate
        expr: |
          rate(http_requests_total{status="500"}[5m]) /
          rate(http_requests_total[5m]) > 0.10
        for: 2m
        labels:
          severity: critical
          component: api
        annotations:
          summary: "CRITICAL: Very high error rate"
          description: "Error rate is above 10% for the last 2 minutes (current: {{ $value | humanizePercentage }})"

  # ============================================================
  # PERFORMANCE ALERTS
  # ============================================================
  - name: performance
    interval: 30s
    rules:
      - alert: SlowRequests
        expr: |
          histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket[5m])
          ) > 10
        for: 5m
        labels:
          severity: warning
          component: api
        annotations:
          summary: "Slow API requests detected"
          description: "95th percentile of request duration is above 10s (current: {{ $value }}s)"

      - alert: SlowSeparations
        expr: |
          histogram_quantile(0.95,
            rate(separation_duration_seconds_bucket[10m])
          ) > 300
        for: 10m
        labels:
          severity: warning
          component: separator
        annotations:
          summary: "Slow audio separations"
          description: "95th percentile of separation duration is above 5 minutes (current: {{ $value }}s)"

      - alert: HighSeparationFailureRate
        expr: |
          rate(separations_total{status="error"}[10m]) /
          rate(separations_total[10m]) > 0.10
        for: 10m
        labels:
          severity: warning
          component: separator
        annotations:
          summary: "High separation failure rate"
          description: "Separation failure rate is above 10% (current: {{ $value | humanizePercentage }})"

  # ============================================================
  # RESOURCE ALERTS
  # ============================================================
  - name: resources
    interval: 30s
    rules:
      - alert: HighCPUUsage
        expr: cpu_usage_percent > 85
        for: 5m
        labels:
          severity: warning
          component: system
        annotations:
          summary: "High CPU usage"
          description: "CPU usage is above 85% for 5 minutes (current: {{ $value }}%)"

      - alert: CriticalCPUUsage
        expr: cpu_usage_percent > 95
        for: 2m
        labels:
          severity: critical
          component: system
        annotations:
          summary: "CRITICAL: CPU usage"
          description: "CPU usage is above 95% (current: {{ $value }}%)"

      - alert: HighMemoryUsage
        expr: memory_percent > 85
        for: 5m
        labels:
          severity: warning
          component: system
        annotations:
          summary: "High memory usage"
          description: "Memory usage is above 85% for 5 minutes (current: {{ $value }}%)"

      - alert: CriticalMemoryUsage
        expr: memory_percent > 95
        for: 2m
        labels:
          severity: critical
          component: system
        annotations:
          summary: "CRITICAL: Memory usage"
          description: "Memory usage is above 95% (current: {{ $value }}%)"

      - alert: LowDiskSpace
        expr: |
          disk_free_bytes{path="/tmp"} /
          (disk_usage_bytes{path="/tmp"} + disk_free_bytes{path="/tmp"}) < 0.10
        for: 5m
        labels:
          severity: warning
          component: system
        annotations:
          summary: "Low disk space on /tmp"
          description: "Less than 10% disk space remaining on /tmp ({{ $value | humanizePercentage }} free)"

      - alert: CriticalDiskSpace
        expr: |
          disk_free_bytes{path="/tmp"} /
          (disk_usage_bytes{path="/tmp"} + disk_free_bytes{path="/tmp"}) < 0.05
        for: 2m
        labels:
          severity: critical
          component: system
        annotations:
          summary: "CRITICAL: Disk space"
          description: "Less than 5% disk space remaining on /tmp ({{ $value | humanizePercentage }} free)"

  # ============================================================
  # GPU ALERTS (if applicable)
  # ============================================================
  - name: gpu
    interval: 30s
    rules:
      - alert: HighGPUMemory
        expr: |
          gpu_memory_used_bytes /
          gpu_memory_total_bytes > 0.90
        for: 5m
        labels:
          severity: warning
          component: gpu
        annotations:
          summary: "High GPU memory usage"
          description: "GPU {{ $labels.device }} memory usage is above 90% (current: {{ $value | humanizePercentage }})"

      - alert: GPUMemoryLeak
        expr: |
          delta(gpu_memory_used_bytes[30m]) > 1e9  # 1GB increase in 30 min
        for: 30m
        labels:
          severity: warning
          component: gpu
        annotations:
          summary: "Possible GPU memory leak"
          description: "GPU {{ $labels.device }} memory increased by more than 1GB in 30 minutes"

  # ============================================================
  # APPLICATION ALERTS
  # ============================================================
  - name: application
    interval: 30s
    rules:
      - alert: TooManyActiveSessions
        expr: active_sessions > 50
        for: 10m
        labels:
          severity: warning
          component: application
        annotations:
          summary: "Too many active sessions"
          description: "More than 50 active sessions (current: {{ $value }})"

      - alert: TempStorageGrowth
        expr: |
          delta(temp_storage_bytes[1h]) > 10e9  # 10GB increase in 1 hour
        for: 1h
        labels:
          severity: warning
          component: application
        annotations:
          summary: "Rapid temp storage growth"
          description: "Temp storage grew by more than 10GB in 1 hour"

      - alert: CircuitBreakerOpen
        expr: |
          # This would need to be exposed as a metric
          # circuit_breaker_state{state="open"} == 1
          # For now, monitor via error rate instead
          rate(errors_total{type="CircuitBreakerOpen"}[5m]) > 0
        for: 1m
        labels:
          severity: warning
          component: application
        annotations:
          summary: "Circuit breaker is open"
          description: "Circuit breaker has been triggered, service may be degraded"

      - alert: NoModelsLoaded
        expr: sum(models_loaded) == 0
        for: 5m
        labels:
          severity: warning
          component: application
        annotations:
          summary: "No models loaded"
          description: "No ML models are currently loaded in memory"

  # ============================================================
  # RATE LIMITING ALERTS
  # ============================================================
  - name: rate_limiting
    interval: 30s
    rules:
      - alert: HighRateLimitHits
        expr: |
          rate(errors_total{type="RateLimitExceeded"}[5m]) > 1
        for: 10m
        labels:
          severity: info
          component: api
        annotations:
          summary: "High rate of rate limit hits"
          description: "Multiple clients are hitting rate limits ({{ $value }} hits/sec)"