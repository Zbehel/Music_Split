# 📊 Music Separator - Monitoring Stack v2.1

## ✨ What's New

Your Music Separator now has **enterprise-grade monitoring and observability**!

### Added Features

✅ **Prometheus Metrics** - Track everything  
✅ **Grafana Dashboards** - Beautiful visualizations  
✅ **Structured Logging** - JSON logs for easy parsing  
✅ **Alerting** - Get notified of issues  
✅ **Resilience Patterns** - Retry, circuit breaker, rate limiting  
✅ **System Monitoring** - CPU, Memory, Disk, GPU  

---

## 🚀 Quick Start (30 seconds)

```bash
# 1. Start everything
./start-monitoring.sh

# Choose option 1 (Start monitoring stack)

# 2. Access Grafana
open http://localhost:3000
# Login: admin / admin

# 3. View Dashboard
# Click: Dashboards → Music Separator - Overview
```

**That's it!** Your monitoring is now running.

---

## 📊 What You Get

### Grafana Dashboard

![Dashboard Preview](https://via.placeholder.com/800x400?text=Grafana+Dashboard)

**Panels:**
- API Status (up/down)
- Total Separations  
- Success Rate %
- Active Sessions
- Request & Separation Rates
- Latency (p50, p95, p99)
- CPU, Memory, Disk Usage
- Error Summary
- Model Usage Statistics

### Metrics Endpoint

```bash
curl http://localhost:8000/metrics
```

Returns Prometheus-compatible metrics:
- `http_requests_total` - Request counter
- `http_request_duration_seconds` - Latency histogram
- `separations_total` - Separation counter
- `separation_duration_seconds` - Processing time
- `cpu_usage_percent` - CPU usage
- `memory_percent` - Memory usage
- `errors_total` - Error counter
- And 20+ more...

### Structured Logs

```bash
# View logs
docker logs music-separator-api

# Filter by level
docker logs music-separator-api 2>&1 | jq 'select(.level=="ERROR")'

# Get separation stats
docker logs music-separator-api 2>&1 | jq 'select(.event_type=="audio_separation")'
```

Example log:
```json
{
  "timestamp": "2024-11-18T10:30:45.123Z",
  "level": "INFO",
  "message": "Separation completed",
  "event_type": "audio_separation",
  "model": "htdemucs_6s",
  "processing_duration_seconds": 45.2,
  "status": "success"
}
```

---

## 🛡️ Resilience Features

### 1. Automatic Retry

Failed operations are automatically retried with exponential backoff.

```python
@retry(max_attempts=3, delay=1.0, backoff=2.0)
def process():
    # Retries: 1s, 2s, 4s delays
    pass
```

### 2. Circuit Breaker

Prevents cascading failures when models fail to load.

**States:**
- **CLOSED** ✅ - Normal operation
- **OPEN** ❌ - Too many failures, reject requests
- **HALF_OPEN** ⏸️ - Testing recovery

Check state: `curl http://localhost:8000/health | jq '.circuit_breaker_state'`

### 3. Rate Limiting

Protects against abuse: **10 requests/minute per IP**

Returns HTTP 429 when exceeded.

---

## 🔔 Alerting

### Pre-configured Alerts

**Critical (immediate action required):**
- API Down > 1 minute
- Error rate > 10%
- CPU > 95%
- Memory > 95%  
- Disk < 5% free

**Warning (investigate soon):**
- Error rate > 5%
- High latency (p95 > 10s)
- CPU > 85%
- Memory > 85%
- Disk < 10% free

### Configure Notifications

Edit `alertmanager.yml` to add Slack/Email:

```yaml
receivers:
  - name: 'critical'
    slack_configs:
      - channel: '#alerts'
        webhook_url: 'YOUR_WEBHOOK_URL'
```

---

## 📁 Architecture

```
┌─────────────────┐
│   Grafana       │ ← Visualization
│  (port 3000)    │
└────────┬────────┘
         │
┌────────▼────────┐
│  Prometheus     │ ← Metrics Storage
│  (port 9090)    │
└────────┬────────┘
         │
         │ scrapes
         │
┌────────▼────────┐
│  API            │ ← Application
│  (port 8000)    │   - Metrics endpoint
│                 │   - Structured logs
│                 │   - Resilience patterns
└─────────────────┘
```

---

## 📖 Documentation

**Complete guides:**
- [docs/MONITORING.md](docs/MONITORING.md) - Full monitoring guide
- [docs/CI-CD.md](docs/CI-CD.md) - CI/CD pipeline
- [docs/KUBERNETES.md](docs/KUBERNETES.md) - Kubernetes deployment

**Key files:**
- `src/metrics.py` - Prometheus metrics
- `src/logging_config.py` - Structured logging
- `src/resilience.py` - Retry, circuit breaker, rate limiting
- `prometheus.yml` - Prometheus config
- `alert_rules.yml` - Alert definitions
- `grafana/dashboards/overview.json` - Main dashboard

---

## 🧪 Testing

### Generate Load

```bash
# Install hey (load generator)
go install github.com/rakyll/hey@latest

# Test API
hey -n 100 -c 10 http://localhost:8000/health

# Watch metrics update in Grafana
```

### Trigger Alerts

```bash
# Trigger high error rate
for i in {1..20}; do
  curl http://localhost:8000/invalid-endpoint
done

# Check alerts
curl http://localhost:9093/api/v1/alerts | jq '.'
```

---

## 🆘 Troubleshooting

### Metrics not showing in Grafana

```bash
# 1. Check Prometheus is scraping
curl http://localhost:9090/targets

# 2. Check API metrics endpoint
curl http://localhost:8000/metrics

# 3. Restart Prometheus
docker-compose -f docker-compose.monitoring.yml restart prometheus
```

### High Memory Usage

```bash
# 1. Check loaded models
curl http://localhost:8000/health | jq '.models_loaded_count'

# 2. Clear cache
curl -X POST http://localhost:8000/clear-cache

# 3. Monitor in Grafana
```

### Alerts Not Firing

```bash
# 1. Check Alertmanager status
curl http://localhost:9093/api/v1/status

# 2. Check alert rules
curl http://localhost:9090/api/v1/rules

# 3. View Prometheus logs
docker logs music-separator-prometheus
```

---

## 🎯 Next Steps

1. **Customize Dashboard**
   - Add panels for your specific needs
   - Create new views

2. **Configure Notifications**
   - Add Slack webhook
   - Set up email alerts

3. **Tune Thresholds**
   - Adjust alert thresholds based on your traffic
   - Review and optimize

4. **Enable More Metrics**
   - Add custom metrics for your use case
   - Track business KPIs

---

## 📊 Example Queries

### Prometheus Queries

```promql
# Request rate
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status="500"}[5m]) / rate(http_requests_total[5m])

# p95 latency  
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Separations per second
rate(separations_total[5m])

# Success rate
sum(rate(separations_total{status="success"}[5m])) / sum(rate(separations_total[5m]))
```

### cURL Examples

```bash
# Health check with full details
curl http://localhost:8000/health | jq '.'

# Get metrics
curl http://localhost:8000/metrics

# Clear model cache
curl -X POST http://localhost:8000/clear-cache

# Clean up old sessions
curl -X POST http://localhost:8000/cleanup-all
```

---

## ✅ Checklist

After setup, verify:

- [ ] Grafana accessible at http://localhost:3000
- [ ] Dashboard showing data
- [ ] Prometheus scraping metrics
- [ ] Alerts configured
- [ ] Logs are JSON formatted
- [ ] Circuit breaker working (check /health)
- [ ] Rate limiting active (test with multiple requests)

---

## 🎉 You're All Set!

Your Music Separator now has:
- ✅ Real-time monitoring
- ✅ Performance tracking
- ✅ Error alerting
- ✅ System observability
- ✅ Production-ready resilience

**Questions?** Check [docs/MONITORING.md](docs/MONITORING.md) for details.

---

**Version**: 2.1.0  
**Created**: 2024-11-18  
**Status**: ✅ Production Ready
