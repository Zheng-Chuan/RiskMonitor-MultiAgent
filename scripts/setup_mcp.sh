#!/bin/bash

# RiskMonitor-MCP Setup Script
# This script helps you set up the MCP server with Docker

set -e

echo "=================================="
echo "RiskMonitor-MCP Setup"
echo "=================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Navigate to project root
cd "$(dirname "$0")/.."

echo "Step 1: Building Docker images..."
docker-compose build

echo ""
echo "Step 2: Starting services..."
docker-compose up -d

echo ""
echo "Step 3: Waiting for MySQL to be ready..."
sleep 10

echo ""
echo "Step 4: Checking service status..."
docker-compose ps

echo ""
echo "=================================="
echo "Setup Complete!"
echo "=================================="
echo ""
echo "Services running:"
echo "  - MySQL Database: localhost:3307"
echo "  - MCP Server: riskmonitor-mcp (container)"
echo "  - phpMyAdmin: http://localhost:8080 (optional, use 'docker-compose --profile tools up -d')"
echo ""
echo "Next steps:"
echo "  1. View MCP logs: docker logs -f riskmonitor-mcp"
echo "  2. Test connection: docker exec -it riskmonitor-mcp python -c 'import pymysql; print(\"OK\")'"
echo "  3. Configure your MCP client (Windsurf/Claude Desktop)"
echo ""
echo "MCP Configuration:"
echo "  Add this to your mcp_config.json:"
echo ""
cat mcp_config.example.json
echo ""
echo "For more details, see docs/MCP_CONFIG.md"
echo ""
