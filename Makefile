.PHONY: help install up down restart logs test test-db test-unit test-integration test-all clean clean-cache shell-db phpmyadmin build mcp-logs mcp-shell setup-mcp test-cov up-infra register-cdc register-cdc-schema run-sentinel ingest-knowledge

help:
	@echo "RiskMonitor-MultiAgent Development Commands"
	@echo "====================================="
	@echo "make install          - Install Python dependencies"
	@echo "make build            - Build Docker images"
	@echo "make up               - Start all Docker containers"
	@echo "make down             - Stop all Docker containers"
	@echo "make restart          - Restart all Docker containers"
	@echo "make logs             - Show all container logs"
	@echo ""
	@echo "MCP Server Commands:"
	@echo "make setup-mcp        - Setup MCP server with Docker"
	@echo "make mcp-logs         - Show MCP server logs"
	@echo "make mcp-shell        - Open shell in MCP container"
	@echo ""
	@echo "Testing Commands:"
	@echo "make test-db          - Test database connection"
	@echo "make test-unit        - Run unit tests"
	@echo "make test-integration - Run integration tests"
	@echo "make test-all         - Run all tests"
	@echo "make test             - Alias for test-all"
	@echo ""
	@echo "Code Quality Commands:"
	@echo "make test-cov         - Run tests with coverage report"
	@echo ""
	@echo "Other Commands:"
	@echo "make clean            - Clean up containers and volumes"
	@echo "make clean-cache      - Clean Python cache files"
	@echo "make shell-db         - Open MySQL shell"
	@echo "make phpmyadmin       - Start with phpMyAdmin (optional tool)"
	@echo ""
	@echo "Week6 CDC Commands:"
	@echo "make up-infra         - Start Kafka/Debezium/Schema Registry stack"
	@echo "make register-cdc     - Register Debezium positions connector"
	@echo "make register-cdc-schema - Register JSON schema to Schema Registry"
	@echo ""
	@echo "Week7 Stream Processing Commands:"
	@echo "make run-sentinel     - Start the Sentinel Service (simple breach detector)"
	@echo ""
	@echo "Week8 Knowledge Base Commands:"
	@echo "make ingest-knowledge - Ingest recent alerts into local knowledge base"

install:
	pip install -r requirements.txt

pylint:
	python -m pylint src tests main.py

lint: pylint
	@echo "Pylint passed!"

test-cov:
	pytest --cov=src --cov-report=html --cov-report=term --cov-report=xml tests/

build:
	docker compose build

up:
	docker compose up -d
	@echo "Waiting for database to be ready..."
	@sleep 5
	@echo "Containers are running!"
	@docker compose ps

up-infra:
	docker compose --profile infra up -d zookeeper kafka kafka-ui debezium schema-registry

register-cdc:
	./scripts/debezium/register_positions_connector.sh

register-cdc-schema:
	./scripts/schema_registry/register_positions_cdc_schema.sh

run-sentinel:
	python ./scripts/run_sentinel.py

ingest-knowledge:
	python ./scripts/knowledge/ingest_alerts.py

setup-mcp:
	@echo "=================================="
	@echo "RiskMonitor-MultiAgent Setup"
	@echo "=================================="
	@echo "Building Docker images..."
	docker compose build
	@echo "Starting services..."
	docker compose up -d
	@echo "Waiting for MySQL to be ready..."
	@sleep 10
	@echo "Containers are running!"
	@docker compose ps

mcp-logs:
	docker logs -f riskmonitor-multiagent

mcp-shell:
	docker exec -it riskmonitor-multiagent /bin/bash

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

test-db:
	@echo "Testing database connection..."
	python tests/diagnostics/db_connection_check.py

test-unit:
	@echo "Running unit tests..."
	pytest tests/unit/ -v --tb=short

test-integration:
	@echo "Running integration tests..."
	@echo "Ensuring containers are running..."
	@docker compose ps mysql | grep -q "Up" || docker compose up -d mysql
	@sleep 5
	pytest tests/integration/ -v --tb=short

test-all: test-db test-unit test-integration
	@echo ""
	@echo "✓ All tests completed!"

test: test-all

clean:
	docker compose down -v
	@echo "All containers and volumes removed"

clean-cache:
	@echo "Cleaning Python cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".DS_Store" -delete
	@echo "Cache files cleaned"

shell-db:
	docker compose exec mysql sh -lc 'mysql -u "$${MYSQL_USER}" -p"$${MYSQL_PASSWORD}" "$${MYSQL_DATABASE}"'

phpmyadmin:
	docker compose --profile tools up -d
	@echo "phpMyAdmin available at http://localhost:8080"
	@echo "Server: mysql"
	@echo "Username: admin"
