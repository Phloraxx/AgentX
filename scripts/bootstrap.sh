#!/bin/bash
set -e

echo "=== AgentX Bootstrap ==="

# Build sandbox images
echo "[1/3] Building sandbox Docker images..."
cd "$(dirname "$0")/../backend/sandbox-images/python"
docker build -t agentx-sandbox-python:latest .
cd "$(dirname "$0")/../backend/sandbox-images/javascript"
docker build -t agentx-sandbox-node:latest .
echo "  ✅ Sandbox images built"

# Install backend deps
echo "[2/3] Installing backend dependencies..."
cd "$(dirname "$0")/../backend"
poetry install 2>/dev/null || pip install -e .
echo "  ✅ Backend deps installed"

# Install frontend deps
echo "[3/3] Installing frontend dependencies..."
cd "$(dirname "$0")/../frontend"
pnpm install 2>/dev/null || npm install
echo "  ✅ Frontend deps installed"

echo ""
echo "=== Bootstrap complete ==="
echo "Run 'python demo_check.py' from backend/ to verify services"
