.PHONY: help install up down restart logs test clean

help:
	@echo "RiskMonitor-MCP Development Commands"
	@echo "====================================="
	@echo "make install    - Install Python dependencies"
	@echo "make up         - Start all Docker containers"
	@echo "make down       - Stop all Docker containers"
	@echo "make restart    - Restart all Docker containers"
	@echo "make logs       - Show container logs"
	@echo "make test-db    - Test database connection"
	@echo "make clean      - Clean up containers and volumes"
	@echo "make shell-db   - Open PostgreSQL shell"
	@echo "make pgadmin    - Start with PgAdmin (optional tool)"

install:
	pip install -r requirements.txt

up:
	docker-compose up -d
	@echo "Waiting for database to be ready..."
	@sleep 5
	@echo "Containers are running!"
	@docker-compose ps

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

test-db:
	python scripts/test_db_connection.py

clean:
	docker-compose down -v
	@echo "All containers and volumes removed"

shell-db:
	docker-compose exec mysql mysql -u admin -priskmonitor2024 riskmonitor

pgadmin:
	docker-compose --profile tools up -d
	@echo "PgAdmin available at http://localhost:5050"
	@echo "Email: admin@riskmonitor.com"
	@echo "Password: admin"
