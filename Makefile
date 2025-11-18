.PHONY: help start stop restart logs build clean health

help:
	@echo "Music Separator - Quick Commands"
	@echo ""
	@echo "Usage:"
	@echo "  make start       - Start all services"
	@echo "  make stop        - Stop all services"
	@echo "  make restart     - Restart all services"
	@echo "  make logs        - Show logs"
	@echo "  make build       - Rebuild images"
	@echo "  make clean       - Remove containers and volumes"
	@echo "  make health      - Check service health"
	@echo ""

start:
	@echo "🚀 Starting services..."
	docker compose -f monitoring/docker-compose.yml up -d

stop:
	@echo "🛑 Stopping services..."
	docker compose -f monitoring/docker-compose.yml down

restart:
	@echo "🔄 Restarting services..."
	docker compose -f monitoring/docker-compose.yml restart

logs:
	docker compose -f monitoring/docker-compose.yml logs -f

logs-api:
	docker compose -f monitoring/docker-compose.yml logs -f api

logs-gradio:
	docker compose -f monitoring/docker-compose.yml logs -f gradio

build:
	@echo "🏗️  Building images..."
	docker compose -f monitoring/docker-compose.yml build

clean:
	@echo "🧹 Cleaning up..."
	docker compose -f monitoring/docker-compose.yml down -v

health:
	@echo "🏥 Checking health..."
	@curl -s http://localhost:8000/health | jq || curl -s http://localhost:8000/health
	@echo ""
	@echo "Services:"
	@docker compose -f monitoring/docker-compose.yml ps
