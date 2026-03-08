.PHONY: help install up down restart logs test test-db test-unit test-integration test-all clean clean-cache shell-db phpmyadmin build mcp-logs mcp-shell setup-mcp test-cov up-kb ingest-knowledge kb-query eval-run eval-compare eval-gate check-llm

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
	@echo "Week8 Knowledge Base Commands:"
	@echo "make up-kb            - Start vector database (Chroma)"
	@echo "make ingest-knowledge - Ingest recent alerts into vector database"
	@echo "make kb-query         - Query vector database, usage: make kb-query QUERY='...' TOP_K=5"
	@echo ""
	@echo "Evaluation Commands:"
	@echo "make eval-run         - Run benchmark, usage: make eval-run RUN_TAG=run1 REPEATS=2"
	@echo "make eval-compare     - Compare two runs, usage: make eval-compare BASE=run1 CAND=run2"
	@echo "make eval-gate        - Apply quality gate, usage: make eval-gate RUN_TAG=run1"
	@echo "make check-llm        - Verify LLM connection (.env: LLM_API_KEY)"

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

ingest-knowledge:
	python ./scripts/knowledge/kb.py ingest-alerts

up-kb:
	docker compose --profile kb up -d chroma

kb-query:
	python ./scripts/knowledge/kb.py query --query "$(QUERY)" --top-k "$(if $(TOP_K),$(TOP_K),5)"

eval-run:
	python -m scripts.eval.run_benchmark --bench "$(if $(BENCH),$(BENCH),eval/benchmarks/explainability_cases.jsonl)" --run-tag "$(if $(RUN_TAG),$(RUN_TAG),baseline)" --model "$(MODEL)" --policy-version "$(POLICY_VERSION)" --prompt-version "$(PROMPT_VERSION)" --hitl "$(if $(HITL),$(HITL),1)" --budget-profile "$(BUDGET_PROFILE)" --repeats "$(if $(REPEATS),$(REPEATS),1)"

eval-compare:
	python -m scripts.eval.compare_runs --base "$(BASE)" --cand "$(CAND)"

eval-gate:
	python -m scripts.eval.quality_gate --run "$(if $(RUN_TAG),$(RUN_TAG),baseline)" --gate "$(if $(GATE),$(GATE),eval/gates/default.json)"

check-llm:
	python scripts/check_llm_connection.py

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
