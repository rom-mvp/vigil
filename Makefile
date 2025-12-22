.PHONY: help build test clean up down logs

# Default target
help:
	@echo "Vigil SaaS - Makefile Commands"
	@echo "=============================="
	@echo "make build     - Build all Docker images"
	@echo "make test      - Run all tests"
	@echo "make up        - Start all services"
	@echo "make down      - Stop all services"
	@echo "make logs      - Tail logs from all services"
	@echo "make clean     - Remove all containers and volumes"
	@echo "make shell-gateway   - Shell into Vigil Gateway"
	@echo "make shell-enclave   - Shell into AgentShield Enclave"
	@echo "make test-unit       - Run unit tests"
	@echo "make test-integration - Run integration tests"

# Build all Docker images
build:
	@echo "🔨 Building Vigil Gateway..."
	docker build -t vigil-gateway:latest services/vigil-gateway
	@echo "🔨 Building AgentShield Enclave..."
	docker build -t agentshield-enclave:latest services/agentshield-enclave -f services/agentshield-enclave/Dockerfile.simulation
	@echo "✅ Build complete!"

# Start all services
up:
	@echo "🚀 Starting Vigil SaaS stack..."
	docker-compose -f docker-compose.saas.yml up -d
	@echo "✅ Services started!"
	@echo "   Vigil Gateway: http://localhost:8000"
	@echo "   Redis: localhost:6379"
	@make health-check

# Stop all services
down:
	@echo "🛑 Stopping services..."
	docker-compose -f docker-compose.saas.yml down
	@echo "✅ Services stopped!"

# View logs
logs:
	docker-compose -f docker-compose.saas.yml logs -f

# Clean everything (including volumes)
clean:
	@echo "🗑️  Cleaning up..."
	docker-compose -f docker-compose.saas.yml down -v
	docker system prune -f
	@echo "✅ Cleanup complete!"

# Health check
health-check:
	@echo "🏥 Checking service health..."
	@sleep 3
	@curl -s http://localhost:8000/health | jq '.' || echo "❌ Gateway not ready"
	@echo "✅ Health check complete"

# Shell into services
shell-gateway:
	docker exec -it vigil-gateway /bin/bash

shell-enclave:
	docker exec -it agentshield-enclave /bin/bash

# Run tests
test:
	@echo "🧪 Running all tests..."
	@make test-unit
	@make test-integration
	@echo "✅ All tests complete!"

test-unit:
	@echo "🧪 Running unit tests..."
	pytest tests/unit -v

test-integration:
	@echo "🧪 Running integration tests..."
	pytest tests/integration -v

test-performance:
	@echo "🧪 Running performance tests..."
	pytest tests/performance -v

# Development helpers
dev:
	@echo "🔧 Starting in development mode..."
	docker-compose -f docker-compose.saas.yml up

install-shared:
	@echo "📦 Installing shared dependencies..."
	pip install -e shared/

lint:
	@echo "🔍 Linting code..."
	ruff check services/vigil-gateway/src services/agentshield-enclave/src
	@echo "✅ Lint complete!"

format:
	@echo "🎨 Formatting code..."
	black services/vigil-gateway/src services/agentshield-enclave/src
	@echo "✅ Format complete!"
