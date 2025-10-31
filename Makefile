.PHONY: help install up down restart logs test test-db test-unit test-integration test-all clean shell-db phpmyadmin build mcp-logs mcp-shell setup-mcp

help:
	@echo "RiskMonitor-MCP Development Commands"
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
	@echo "Other Commands:"
	@echo "make clean            - Clean up containers and volumes"
	@echo "make shell-db         - Open MySQL shell"
	@echo "make phpmyadmin       - Start with phpMyAdmin (optional tool)"

install:
	pip install -r requirements.txt

build:
	docker-compose build

up:
	docker-compose up -d
	@echo "Waiting for database to be ready..."
	@sleep 5
	@echo "Containers are running!"
	@docker-compose ps

setup-mcp:
	@./scripts/setup_mcp.sh

mcp-logs:
	docker logs -f riskmonitor-mcp

mcp-shell:
	docker exec -it riskmonitor-mcp /bin/bash

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

test-db:
	@echo "Testing database connection..."
	python scripts/test_db_connection.py

test-unit:
	@echo "Running unit tests..."
	pytest tests/unit/ -v --tb=short

test-integration:
	@echo "Running integration tests..."
	@echo "Ensuring containers are running..."
	@docker-compose ps mysql | grep -q "Up" || docker-compose up -d mysql
	@sleep 5
	pytest tests/integration/ -v --tb=short

test-all: test-db test-unit test-integration
	@echo ""
	@echo "✓ All tests completed!"

test: test-all

clean:
	docker-compose down -v
	@echo "All containers and volumes removed"

shell-db:
	docker-compose exec mysql mysql -u admin -priskmonitor2024 riskmonitor

phpmyadmin:
	docker-compose --profile tools up -d
	@echo "phpMyAdmin available at http://localhost:8080"
	@echo "Server: mysql"
	@echo "Username: admin"
	@echo "Password: riskmonitor2024"
