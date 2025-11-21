#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#  MUSIC SEPARATOR - MONITORING QUICK START
# ═══════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
ORANGE='\033[0;33m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  📊 MUSIC SEPARATOR - MONITORING STACK"
echo "════════════════════════════════════════════════════════════"
echo ""

# Ensure we are in the project root
cd "$(dirname "$0")/../.."

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running"
    exit 1
fi

# Create temp directories
mkdir -p tmp/music-separator
mkdir -p results

echo -e "${GREEN}✅ Docker found and running${NC}"
echo ""

# Menu
echo "Choose an action:"
echo ""
echo "1) Start monitoring stack (Prometheus + Grafana + API)"
echo "2) Stop monitoring stack"
echo "3) View logs"
echo "4) Check status"
echo "5) Restart services"
echo "6) Clean up (⚠️  removes all data)"
echo "7) Exit"
echo ""
read -p "Your choice (1-7): " choice


# Use monitoring docker-compose (unified)
COMPOSE_FILE="monitoring/docker-compose.yml"
DOCKERFILE="dockerfile"


case $choice in
    1)
        echo ""
        echo -e "${BLUE}🚀 Starting monitoring stack...${NC}"
        echo ""
        

        # Build if needed
        
        if ! docker images | grep -q "music-separator"; then
            echo "Building Docker image..."
            docker build -t music-separator:latest .
        fi
        
        # Start services
        docker-compose -f $COMPOSE_FILE up -d
        
        echo ""
        echo "Waiting for services to be ready..."
        sleep 10
        
        # Check health
        echo ""
        echo -e "${BLUE}Checking services...${NC}"
        docker-compose -f $COMPOSE_FILE ps
        
        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo -e "${GREEN}✅ Monitoring stack started!${NC}"
        echo "════════════════════════════════════════════════════════════"
        echo ""
        echo "📊 Access points:"
        echo ""
        echo "  Grafana:      http://localhost:3000"
        echo "                Login: admin / admin"
        echo ""
        echo "  Prometheus:   http://localhost:9090"
        echo ""
        echo "  API:          http://localhost:8000/docs"
        echo "  Metrics:      http://localhost:8000/metrics"
        echo ""
        echo "  Gradio:       http://localhost:7860"
        echo ""
        echo "  Alertmanager: http://localhost:9093"
        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo ""
        echo "View logs with: ./start-monitoring.sh → option 3"
        echo ""
        ;;
        
    2)
        echo ""
        echo -e "${YELLOW}Stopping monitoring stack...${NC}"
        docker-compose -f $COMPOSE_FILE down
        echo -e "${GREEN}✅ Stopped${NC}"
        ;;
        
    3)
        echo ""
        echo "Which logs to view?"
        echo ""
        echo "1) API"
        echo "2) Gradio"
        echo "3) Prometheus"
        echo "4) Grafana"
        echo "5) Redis"
        echo "6) Celery Worker"
        echo "7) All"
        echo ""
        read -p "Choice: " log_choice
        
        case $log_choice in
            1) docker logs -f music-separator-api ;;
            2) docker logs -f music-separator-gradio ;;
            3) docker logs -f music-separator-prometheus ;;
            4) docker logs -f music-separator-grafana ;;
            5) docker logs -f music-separator-redis ;;
            6) docker logs -f music-separator-celery ;;
            7) docker-compose -f $COMPOSE_FILE logs -f ;;
            *) echo "Invalid choice" ;;
        esac
        ;;
        
    4)
        echo ""
        echo -e "${BLUE}Service Status:${NC}"
        echo ""
        docker-compose -f $COMPOSE_FILE ps
        echo ""
        
        # Test API
        echo -e "${BLUE}API Health:${NC}"
        curl -s http://localhost:8000/health | jq '.' || echo "API not responding"
        echo ""
        
        # Test Prometheus
        echo -e "${BLUE}Prometheus Status:${NC}"
        curl -s http://localhost:9090/-/healthy && echo "✅ Healthy" || echo "❌ Not healthy"
        echo ""
        
        # Test Grafana
        echo -e "${BLUE}Grafana Status:${NC}"
        curl -s http://localhost:3000/api/health && echo "✅ Healthy" || echo "❌ Not healthy"
        echo ""
        ;;
        
    5)
        echo ""
        echo -e "${YELLOW}Restarting services...${NC}"
        docker-compose -f $COMPOSE_FILE restart
        echo -e "${GREEN}✅ Restarted${NC}"
        ;;
        
    6)
        echo ""
        echo -e "${RED}⚠️  WARNING: This will remove all data!${NC}"
        echo ""
        read -p "Type 'yes' to confirm: " confirm
        
            if [ "$confirm" = "yes" ]; then
            echo ""
            echo "Stopping and removing everything..."
            docker-compose -f $COMPOSE_FILE down -v
                # Ask whether to also remove built images
                echo ""
                echo -e "${ORANGE}Also remove built images (music-separator:latest)?${NC}"
                read -p "Type 'yes' to confirm:" remove_images
                if [ "$remove_images" = "yes" ]; then
                    echo "Removing images..."
                    # Use docker-compose to remove images built by the service
                    docker-compose -f $COMPOSE_FILE down --rmi all -v --remove-orphans
                    echo ""
                    echo -e "${GREEN}✅ Images removed${NC}"
                fi
            echo ""
            echo -e "${GREEN}✅ Cleaned up${NC}"
        else
            echo "Cancelled"
        fi
        ;;
        
    7)
        echo "Bye!"
        exit 0
        ;;
        
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""