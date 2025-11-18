# 📊 Music Separator - Monitoring & Observability Guide

## 🎯 Overview

This guide covers the complete monitoring, logging, and observability stack for the Music Separator application.

**What's Included:**
- ✅ Prometheus for metrics collection
- ✅ Grafana for visualization
- ✅ Structured JSON logging
- ✅ Alertmanager for notifications
- ✅ Resilience patterns (retry, circuit breaker, rate limiting)
- ✅ System metrics (CPU, Memory, Disk, GPU)
- ✅ Application metrics (requests, separations, errors)

---

## 🚀 Quick Start

### 1. Start with Monitoring Stack

```bash
# Start everything (API + Gradio + Monitoring)
docker-compose -f docker-compose.monitoring.yml up -d

# Check status
docker-compose -f docker-compose.monitoring.yml ps
```

### 2. Access Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3000 | admin / admin |
| **Prometheus** | http://localhost:9090 | - |
| **API Docs** | http://localhost:8000/docs | - |
| **API Metrics** | http://localhost:8000/metrics | - |
| **Alertmanager** | http://localhost:9093 | - |

### 3. View Metrics

```bash
# API metrics endpoint
curl http://localhost:8000/metrics

# Prometheus query example
curl 'http://localhost:9090/api/v1/query?query=up'
```

---

## 📊 Grafana Dashboards

### Main Dashboard: Overview

Access: http://localhost:3000/dashboards

**Panels:**
1. **API Status** - Is the API up/down
2. **Total Separations** - Cumulative count
3. **Success Rate** - Percentage of successful separations
4. **Active Sessions** - Current processing sessions
5. **Request Rate** - HTTP requests per second
6. **Separation Rate** - Audio separations per second
7. **Request Duration** - p50, p95, p99 latencies
8. **Separation Duration** - Processing time percentiles
9. **CPU Usage** - System CPU percentage
10. **Memory Usage** - System memory percentage
11. **Disk Usage** - /tmp directory usage
12. **Error Summary** - Error types and rates
13. **Models Usage** - Which models are being used

### Creating Custom Dashboards

```bash
# Import dashboard from Grafana UI
1. Go to Grafana → Dashboards → Import
2. Upload overview.json
3. Select Prometheus datasource
```

---

## 🔔 Alerting

### Alert Rules

Located in `alert_rules.yml`:

**Critical Alerts:**
- APIDown - API has been down > 1 minute
- VeryHighErrorRate - Error rate > 10%
- CriticalCPUUsage - CPU > 95%
- CriticalMemoryUsage - Memory > 95%
- CriticalDiskSpace - Disk < 5% free

**Warning Alerts:**
- HighErrorRate - Error rate > 5%
- SlowRequests - p95 latency > 10s
- SlowSeparations - p95 separation time > 5 minutes
- HighCPUUsage - CPU > 85%
- HighMemoryUsage - Memory > 85%
- LowDiskSpace - Disk < 10% free

### Configure Notifications

Edit `alertmanager.yml`:

#### Slack Integration

```yaml
global:
  slack_api_url: 'YOUR_SLACK_WEBHOOK_URL'

receivers:
  - name: 'critical'
    slack_configs:
      - channel: '#alerts-critical'
        title: '🚨 CRITICAL Alert'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

#### Email Integration

```yaml
receivers:
  - name: 'critical'
    email_configs:
      - to: 'ops@example.com'
        from: 'alertmanager@example.com'
        smarthost: 'smtp.gmail.com:587'
        auth_username: 'your-email@example.com'
        auth_password: 'your-app-password'
```

---

## 📝 Structured Logging

### Log Format

All logs are in JSON format for easy parsing:

```json
{
  "timestamp": "2024-11-18T10:30:45.123Z",
  "level": "INFO",
  "logger": "src.api",
  "message": "Separation completed",
  "module": "api",
  "function": "separate_audio",
  "line": 234,
  "event_type": "audio_separation",
  "model": "htdemucs_6s",
  "audio_duration_seconds": 180.5,
  "processing_duration_seconds": 45.2,
  "status": "success",
  "session_id": "abc123"
}
```

### View Logs

```bash
# API logs
docker logs -f music-separator-api

# Filter by level
docker logs music-separator-api 2>&1 | jq 'select(.level=="ERROR")'

# Filter by event type
docker logs music-separator-api 2>&1 | jq 'select(.event_type=="audio_separation")'

# Get separation stats
docker logs music-separator-api 2>&1 | jq 'select(.event_type=="audio_separation") | {model, duration: .processing_duration_seconds, status}'
```

### Log to File

Update docker-compose.yml:

```yaml
api:
  volumes:
    - ./logs:/var/log/app
  environment:
    - LOG_FILE=/var/log/app/api.log
```

---

## 🛡️ Resilience Patterns

### 1. Retry Logic

Automatically retries failed operations with exponential backoff.

**Configuration:**
```python
from src.resilience import retry

@retry(max_attempts=3, delay=1.0, backoff=2.0)
def flaky_operation():
    # Will retry up to 3 times with delays: 1s, 2s, 4s
    pass
```

**Metrics:**
- Track retries via error logs
- Monitor `RetryExhausted` errors

### 2. Circuit Breaker

Prevents cascading failures by stopping requests to failing services.

**States:**
- **CLOSED** - Normal operation
- **OPEN** - Too many failures, reject requests
- **HALF_OPEN** - Testing if service recovered

**Configuration:**
```python
from src.resilience import CircuitBreaker

cb = CircuitBreaker(
    failure_threshold=5,  # Open after 5 failures
    timeout=60.0          # Try recovery after 60s
)
```

**Monitoring:**
- Check circuit breaker state in `/health`
- Alert on `CircuitBreakerOpen` errors

### 3. Rate Limiting

Limits requests per IP to prevent abuse.

**Configuration:**
- Default: 10 requests per minute per IP
- Returns HTTP 429 when exceeded

**Monitoring:**
```bash
# Check rate limit hits
curl 'http://localhost:9090/api/v1/query?query=rate(errors_total{type="RateLimitExceeded"}[5m])'
```

---

## 📈 Key Metrics

### API Metrics

```promql
# Request rate
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status="500"}[5m]) / rate(http_requests_total[5m])

# p95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

### Separation Metrics

```promql
# Separations per second
rate(separations_total[5m])

# Success rate
sum(rate(separations_total{status="success"}[5m])) / sum(rate(separations_total[5m]))

# p95 processing time
histogram_quantile(0.95, rate(separation_duration_seconds_bucket[5m]))
```

### System Metrics

```promql
# CPU usage
cpu_usage_percent

# Memory usage
memory_percent

# Disk usage
disk_usage_bytes{path="/tmp"} / (disk_usage_bytes{path="/tmp"} + disk_free_bytes{path="/tmp"})
```

---

## 🔍 Troubleshooting

### High Error Rate

```bash
# 1. Check error types
docker logs music-separator-api 2>&1 | jq 'select(.level=="ERROR")' | jq -r '.error_type' | sort | uniq -c

# 2. View recent errors
docker logs music-separator-api --tail=100 2>&1 | jq 'select(.level=="ERROR")'

# 3. Check Prometheus
curl 'http://localhost:9090/api/v1/query?query=sum by (type) (rate(errors_total[5m]))'
```

### Slow Requests

```bash
# 1. Check p95 latency in Grafana
# 2. View slow request logs
docker logs music-separator-api 2>&1 | jq 'select(.event_type=="http_request" and .duration_seconds > 10)'

# 3. Check if circuit breaker is open
curl http://localhost:8000/health | jq '.circuit_breaker_state'
```

### High Memory Usage

```bash
# 1. Check current usage
curl http://localhost:8000/health | jq '.models_loaded_count'

# 2. Clear model cache
curl -X POST http://localhost:8000/clear-cache

# 3. Monitor in Grafana
# Memory Usage panel
```

### Circuit Breaker Open

```bash
# 1. Check state
curl http://localhost:8000/health | jq '.circuit_breaker_state'

# 2. View errors that triggered it
docker logs music-separator-api 2>&1 | jq 'select(.message | contains("Circuit breaker"))'

# 3. Wait for timeout or manually reset
# (Circuit breaker will auto-reset after timeout)
```

---

## 🧪 Testing Monitoring

### Generate Test Load

```bash
# Install hey (HTTP load generator)
go install github.com/rakyll/hey@latest

# Test API
hey -n 100 -c 10 http://localhost:8000/health

# Test separation endpoint (need audio file)
for i in {1..10}; do
  curl -X POST http://localhost:8000/separate \
    -F "file=@test.mp3" \
    -F "model_name=htdemucs_6s" &
done
```

### Trigger Alerts

```bash
# Trigger high error rate
for i in {1..20}; do
  curl http://localhost:8000/invalid-endpoint
done

# Check alerts in Alertmanager
curl http://localhost:9093/api/v1/alerts
```

---

## 📁 File Structure

```
.
├── src/
│   ├── api.py              # Enhanced API with monitoring
│   ├── metrics.py          # Prometheus metrics
│   ├── logging_config.py   # Structured logging
│   └── resilience.py       # Retry, circuit breaker, rate limiting
├── prometheus.yml          # Prometheus configuration
├── alert_rules.yml         # Alert definitions
├── alertmanager.yml        # Alert routing
├── grafana/
│   ├── dashboards/
│   │   └── overview.json   # Main dashboard
│   └── datasources/
│       └── prometheus.yml  # Datasource config
└── docker-compose.monitoring.yml
```

---

## 🎯 Best Practices

1. **Monitor Everything**
   - Track all critical metrics
   - Set up alerts for anomalies
   - Review dashboards regularly

2. **Use Structured Logs**
   - Always use JSON format
   - Include context (request_id, session_id)
   - Make logs searchable

3. **Set Appropriate Thresholds**
   - Don't alert on noise
   - Tune thresholds based on actual usage
   - Review and adjust regularly

4. **Document Runbooks**
   - Create playbooks for common alerts
   - Document troubleshooting steps
   - Keep them up to date

5. **Regular Maintenance**
   - Clean up old logs
   - Archive old metrics
   - Update dashboards

---

## 🆘 Support

For issues or questions:
1. Check logs: `docker logs music-separator-api`
2. Check metrics: http://localhost:9090
3. Check dashboards: http://localhost:3000
4. Review alerts: http://localhost:9093

---

**Version**: 2.1.0  
**Last Updated**: 2024-11-18
