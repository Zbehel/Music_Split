# 🍳 Monitoring Recipes - Practical Examples

Quick copy-paste examples for common monitoring tasks.

---

## 🚀 Getting Started

### Start Full Stack

```bash
./start-monitoring.sh
# Choose: 1 (Start monitoring stack)
```

### Access Services

```bash
# Grafana (Dashboards)
open http://localhost:3000
# Login: admin / admin

# Prometheus (Metrics)
open http://localhost:9090

# API Documentation
open http://localhost:8000/docs

# API Metrics
open http://localhost:8000/metrics
```

---

## 📊 Prometheus Queries

Copy-paste these into Prometheus UI (http://localhost:9090/graph):

### Request Metrics

```promql
# Total requests per second
rate(http_requests_total[5m])

# Requests by status code
sum by (status) (rate(http_requests_total[5m]))

# Error rate (%)
(rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])) * 100

# p50 latency
histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[5m]))

# p95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# p99 latency
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
```

### Separation Metrics

```promql
# Separations per second
rate(separations_total[5m])

# Success rate (%)
(sum(rate(separations_total{status="success"}[5m])) / sum(rate(separations_total[5m]))) * 100

# Separations by model
sum by (model) (rate(separations_total[5m]))

# Failed separations
sum(rate(separations_total{status="error"}[5m]))

# Average separation time
rate(separation_duration_seconds_sum[5m]) / rate(separation_duration_seconds_count[5m])

# p95 separation time
histogram_quantile(0.95, rate(separation_duration_seconds_bucket[5m]))
```

### System Metrics

```promql
# CPU usage
cpu_usage_percent

# Memory usage (%)
memory_percent

# Disk usage (%)
(disk_usage_bytes{path="/tmp"} / (disk_usage_bytes{path="/tmp"} + disk_free_bytes{path="/tmp"})) * 100

# GPU memory usage (%)
(gpu_memory_used_bytes / gpu_memory_total_bytes) * 100
```

### Error Tracking

```promql
# Errors per second
rate(errors_total[5m])

# Errors by type
sum by (type) (rate(errors_total[5m]))

# Top error endpoints
topk(5, sum by (endpoint) (rate(errors_total[5m])))
```

---

## 🔍 Log Queries

### View All Logs

```bash
# Follow all logs
docker logs -f music-separator-api

# Last 100 lines
docker logs --tail 100 music-separator-api

# Since 1 hour ago
docker logs --since 1h music-separator-api
```

### Filter by Level

```bash
# Only errors
docker logs music-separator-api 2>&1 | jq 'select(.level=="ERROR")'

# Only warnings and errors
docker logs music-separator-api 2>&1 | jq 'select(.level=="ERROR" or .level=="WARNING")'

# Debug logs
docker logs music-separator-api 2>&1 | jq 'select(.level=="DEBUG")'
```

### Filter by Event Type

```bash
# Separation events
docker logs music-separator-api 2>&1 | jq 'select(.event_type=="audio_separation")'

# HTTP requests
docker logs music-separator-api 2>&1 | jq 'select(.event_type=="http_request")'

# Errors
docker logs music-separator-api 2>&1 | jq 'select(.event_type=="error")'

# Model loads
docker logs music-separator-api 2>&1 | jq 'select(.event_type=="model_load")'
```

### Extract Specific Fields

```bash
# Get separation durations
docker logs music-separator-api 2>&1 | \
  jq -r 'select(.event_type=="audio_separation") | .processing_duration_seconds'

# Get error messages
docker logs music-separator-api 2>&1 | \
  jq -r 'select(.level=="ERROR") | .message'

# Get models used
docker logs music-separator-api 2>&1 | \
  jq -r 'select(.event_type=="audio_separation") | .model' | sort | uniq -c
```

### Log Analysis

```bash
# Count errors by type
docker logs music-separator-api 2>&1 | \
  jq -r 'select(.level=="ERROR") | .error_type' | sort | uniq -c

# Average separation time by model
docker logs music-separator-api 2>&1 | \
  jq -r 'select(.event_type=="audio_separation") | "\(.model) \(.processing_duration_seconds)"' | \
  awk '{sum[$1]+=$2; count[$1]++} END {for (model in sum) print model, sum[model]/count[model]}'

# Success vs failure count
docker logs music-separator-api 2>&1 | \
  jq -r 'select(.event_type=="audio_separation") | .status' | sort | uniq -c
```

---

## 🧪 Testing & Load Generation

### Health Check

```bash
# Simple health check
curl http://localhost:8000/health

# Health check with details
curl http://localhost:8000/health | jq '.'

# Check circuit breaker state
curl http://localhost:8000/health | jq '.circuit_breaker_state'

# Check loaded models
curl http://localhost:8000/health | jq '.models_loaded'
```

### Generate Load

```bash
# Install hey (HTTP load generator)
go install github.com/rakyll/hey@latest

# Test health endpoint
hey -n 1000 -c 10 http://localhost:8000/health

# Test with specific duration
hey -z 30s -c 5 http://localhost:8000/health

# Save results
hey -n 100 -c 10 http://localhost:8000/health > load_test.txt
```

### Test Separation Endpoint

```bash
# Single separation
curl -X POST http://localhost:8000/separate \
  -F "file=@test.mp3" \
  -F "model_name=htdemucs_6s"

# Multiple separations in parallel
for i in {1..5}; do
  curl -X POST http://localhost:8000/separate \
    -F "file=@test.mp3" \
    -F "model_name=htdemucs_6s" &
done
wait

# Measure time
time curl -X POST http://localhost:8000/separate \
  -F "file=@test.mp3" \
  -F "model_name=htdemucs_6s"
```

### Trigger Rate Limiting

```bash
# Send 15 requests quickly (limit is 10/minute)
for i in {1..15}; do
  curl http://localhost:8000/health
  echo ""
done

# Should see HTTP 429 after 10 requests
```

### Trigger Circuit Breaker

```bash
# This is harder - need to cause model loading failures
# Usually happens with invalid model names or resource exhaustion

# Try invalid model
for i in {1..10}; do
  curl -X POST http://localhost:8000/separate \
    -F "file=@test.mp3" \
    -F "model_name=invalid_model"
done

# Check circuit breaker state
curl http://localhost:8000/health | jq '.circuit_breaker_state'
```

---

## 🔔 Alert Testing

### Check Alert Status

```bash
# All alerts
curl http://localhost:9093/api/v1/alerts | jq '.'

# Active alerts only
curl http://localhost:9093/api/v1/alerts | jq '.data[] | select(.status.state=="active")'

# Firing alerts
curl http://localhost:9093/api/v1/alerts | jq '.data[] | select(.status.state=="firing")'
```

### Trigger High Error Rate Alert

```bash
# Generate errors
for i in {1..50}; do
  curl http://localhost:8000/invalid-endpoint
done

# Wait 5 minutes for alert to fire
# Check: curl http://localhost:9093/api/v1/alerts | jq '.data[] | select(.labels.alertname=="HighErrorRate")'
```

### Silence Alerts

```bash
# Create silence (replace matchers as needed)
curl -X POST http://localhost:9093/api/v1/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [
      {"name": "alertname", "value": "HighErrorRate", "isRegex": false}
    ],
    "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%S.000Z)'",
    "endsAt": "'$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%S.000Z)'",
    "comment": "Planned maintenance"
  }'

# List silences
curl http://localhost:9093/api/v1/silences | jq '.'

# Delete silence
curl -X DELETE http://localhost:9093/api/v1/silence/SILENCE_ID
```

---

## 📊 Grafana Recipes

### Import Dashboard

```bash
# Via UI:
# 1. Go to http://localhost:3000
# 2. Click + → Import
# 3. Upload grafana/dashboards/overview.json

# Via API:
curl -X POST http://admin:admin@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @grafana/dashboards/overview.json
```

### Export Dashboard

```bash
# Get dashboard UID first
curl http://admin:admin@localhost:3000/api/search?type=dash-db | jq '.'

# Export dashboard
curl http://admin:admin@localhost:3000/api/dashboards/uid/DASHBOARD_UID | jq '.' > backup.json
```

### Create Snapshot

```bash
# From UI: Dashboard → Share → Snapshot → Publish to snapshots.raintank.io
```

---

## 🧹 Maintenance Tasks

### Clear Model Cache

```bash
curl -X POST http://localhost:8000/clear-cache
```

### Clean Up Old Sessions

```bash
# Single session
curl -X DELETE http://localhost:8000/cleanup/SESSION_ID

# All sessions (⚠️  destructive)
curl -X POST http://localhost:8000/cleanup-all
```

### Restart Services

```bash
# Restart API
docker-compose -f docker-compose.monitoring.yml restart api

# Restart all
docker-compose -f docker-compose.monitoring.yml restart

# Restart Prometheus (reload config)
curl -X POST http://localhost:9090/-/reload
```

### Backup Data

```bash
# Backup Prometheus data
docker run --rm -v music-separator-prometheus:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/prometheus-backup.tar.gz /data

# Backup Grafana data
docker run --rm -v music-separator-grafana:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/grafana-backup.tar.gz /data
```

### Restore Data

```bash
# Restore Prometheus
docker run --rm -v music-separator-prometheus:/data -v $(pwd):/backup \
  ubuntu tar xzf /backup/prometheus-backup.tar.gz -C /

# Restore Grafana
docker run --rm -v music-separator-grafana:/data -v $(pwd):/backup \
  ubuntu tar xzf /backup/grafana-backup.tar.gz -C /
```

---

## 🔬 Advanced Queries

### Request Duration by Endpoint

```promql
histogram_quantile(0.95,
  sum by (endpoint, le) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
```

### Error Rate by Endpoint

```promql
sum by (endpoint) (
  rate(http_requests_total{status=~"5.."}[5m])
) /
sum by (endpoint) (
  rate(http_requests_total[5m])
) * 100
```

### Top 5 Slowest Models

```promql
topk(5,
  histogram_quantile(0.95,
    sum by (model, le) (
      rate(separation_duration_seconds_bucket[10m])
    )
  )
)
```

### Memory Growth Rate

```promql
# MB per hour
rate(memory_usage_bytes[1h]) * 3600 / 1024 / 1024
```

### Disk Space Remaining Time

```promql
# Hours until disk full (assuming current rate)
disk_free_bytes / rate(temp_storage_bytes[1h]) / 3600
```

---

## 🎯 Troubleshooting Recipes

### API Not Responding

```bash
# 1. Check container status
docker ps | grep music-separator-api

# 2. Check logs
docker logs --tail 100 music-separator-api

# 3. Check resource usage
docker stats music-separator-api

# 4. Test health endpoint
curl -v http://localhost:8000/health

# 5. Restart
docker-compose -f docker-compose.monitoring.yml restart api
```

### High Memory Usage

```bash
# 1. Check loaded models
curl http://localhost:8000/health | jq '.models_loaded'

# 2. Clear cache
curl -X POST http://localhost:8000/clear-cache

# 3. Check active sessions
curl 'http://localhost:9090/api/v1/query?query=active_sessions'

# 4. Clean up old sessions
curl -X POST http://localhost:8000/cleanup-all

# 5. Monitor in Grafana
open http://localhost:3000
```

### Metrics Not Showing

```bash
# 1. Check metrics endpoint
curl http://localhost:8000/metrics

# 2. Check Prometheus targets
curl http://localhost:9090/targets

# 3. Check Prometheus logs
docker logs music-separator-prometheus --tail 50

# 4. Reload Prometheus config
curl -X POST http://localhost:9090/-/reload

# 5. Restart Prometheus
docker-compose -f docker-compose.monitoring.yml restart prometheus
```

### Alerts Not Firing

```bash
# 1. Check alert rules loaded
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.type=="alerting")'

# 2. Check alert status
curl http://localhost:9090/api/v1/alerts

# 3. Check Alertmanager logs
docker logs music-separator-alertmanager --tail 50

# 4. Test alert manually
# Trigger high error rate (see above)

# 5. Check Alertmanager config
docker exec music-separator-alertmanager cat /etc/alertmanager/alertmanager.yml
```

---

## 💡 Pro Tips

### Quick Dashboard Access

```bash
# Add to ~/.bashrc or ~/.zshrc
alias mon-grafana='open http://localhost:3000'
alias mon-prom='open http://localhost:9090'
alias mon-api='open http://localhost:8000/docs'
alias mon-metrics='curl http://localhost:8000/metrics'
alias mon-health='curl http://localhost:8000/health | jq'
```

### Watch Metrics Live

```bash
# Watch request rate
watch -n 1 'curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total[1m])" | jq ".data.result[0].value[1]"'

# Watch active sessions
watch -n 2 'curl -s "http://localhost:9090/api/v1/query?query=active_sessions" | jq ".data.result[0].value[1]"'

# Watch CPU usage
watch -n 1 'curl -s "http://localhost:9090/api/v1/query?query=cpu_usage_percent" | jq ".data.result[0].value[1]"'
```

### Quick Log Analysis

```bash
# Add to ~/.bashrc
alias logs-errors='docker logs music-separator-api 2>&1 | jq "select(.level==\"ERROR\")"'
alias logs-separations='docker logs music-separator-api 2>&1 | jq "select(.event_type==\"audio_separation\")"'
alias logs-stats='docker logs music-separator-api 2>&1 | jq -r "select(.event_type==\"audio_separation\") | \"\(.model) \(.processing_duration_seconds)\"" | awk "{sum[\$1]+=\$2; count[\$1]++} END {for (model in sum) print model, sum[model]/count[model]}"'
```

---

**Happy Monitoring!** 📊

For more details, see [docs/MONITORING.md](docs/MONITORING.md)
