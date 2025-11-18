#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#  DEBUG SCRIPT - Check API Health Issues
# ═══════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  🔍 API HEALTH DEBUG"
echo "════════════════════════════════════════════════════════════"
echo ""

# Check if container is running
echo -e "${BLUE}1. Checking container status...${NC}"
if docker ps | grep -q "music-separator-api"; then
    echo -e "${GREEN}✅ Container is running${NC}"
else
    echo -e "${RED}❌ Container is not running${NC}"
    echo ""
    echo "Checking if container exists but stopped..."
    docker ps -a | grep music-separator-api || echo "Container doesn't exist"
    exit 1
fi
echo ""

# Check container logs
echo -e "${BLUE}2. Recent container logs:${NC}"
echo "─────────────────────────────────────────────────────────────"
docker logs --tail 50 music-separator-api
echo "─────────────────────────────────────────────────────────────"
echo ""

# Check if port 8000 is accessible from inside container
echo -e "${BLUE}3. Testing health endpoint from inside container...${NC}"
if docker exec music-separator-api curl -f http://localhost:8000/health 2>/dev/null; then
    echo -e "${GREEN}✅ Health endpoint responding inside container${NC}"
else
    echo -e "${RED}❌ Health endpoint not responding inside container${NC}"
    echo ""
    echo "Trying to check if uvicorn is running..."
    docker exec music-separator-api ps aux | grep uvicorn || echo "Uvicorn not found"
fi
echo ""

# Check if port is accessible from host
echo -e "${BLUE}4. Testing health endpoint from host...${NC}"
if curl -f http://localhost:8000/health 2>/dev/null; then
    echo -e "${GREEN}✅ Health endpoint accessible from host${NC}"
    curl http://localhost:8000/health | jq '.'
else
    echo -e "${RED}❌ Health endpoint not accessible from host${NC}"
fi
echo ""

# Check Python imports
echo -e "${BLUE}5. Testing Python imports...${NC}"
docker exec music-separator-api python -c "
try:
    from src.metrics import http_requests_total
    print('✅ src.metrics OK')
except Exception as e:
    print(f'❌ src.metrics FAILED: {e}')

try:
    from src.logging_config import setup_logging
    print('✅ src.logging_config OK')
except Exception as e:
    print(f'❌ src.logging_config FAILED: {e}')

try:
    from src.resilience import retry
    print('✅ src.resilience OK')
except Exception as e:
    print(f'❌ src.resilience FAILED: {e}')

try:
    from src.api import app
    print('✅ src.api OK')
except Exception as e:
    print(f'❌ src.api FAILED: {e}')
"
echo ""

# Check dependencies
echo -e "${BLUE}6. Checking required dependencies...${NC}"
docker exec music-separator-api python -c "
import sys
required = ['prometheus_client', 'psutil', 'fastapi', 'uvicorn']
for pkg in required:
    try:
        __import__(pkg)
        print(f'✅ {pkg} installed')
    except ImportError:
        print(f'❌ {pkg} MISSING')
"
echo ""

# Get container resource usage
echo -e "${BLUE}7. Container resource usage:${NC}"
docker stats --no-stream music-separator-api
echo ""

# Check healthcheck status
echo -e "${BLUE}8. Healthcheck status:${NC}"
docker inspect music-separator-api | jq '.[0].State.Health'
echo ""

echo "════════════════════════════════════════════════════════════"
echo "  Debug complete!"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Common issues:"
echo ""
echo "1. Missing dependencies:"
echo "   → Add to requirements.txt: prometheus-client, psutil"
echo ""
echo "2. Import errors:"
echo "   → Check that all src/*.py files are present"
echo ""
echo "3. Port conflict:"
echo "   → Check if port 8000 is already in use"
echo ""
echo "4. Memory issues:"
echo "   → Check Docker memory allocation"
echo ""
echo "To fix, try:"
echo "  docker-compose -f docker-compose.monitoring.yml down"
echo "  docker-compose -f docker-compose.monitoring.yml build --no-cache"
echo "  docker-compose -f docker-compose.monitoring.yml up -d"
echo ""
