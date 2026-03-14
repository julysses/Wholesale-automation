#!/usr/bin/env bash
# WholesaleOS — local startup script (no Docker required)
# Usage: ./start.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Check .env ─────────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  echo "⚠  No .env found. Copying from .env.example..."
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "   Edit .env with your API keys, then re-run this script."
  exit 1
fi

# ── Python deps ────────────────────────────────────────────────────────────────
echo "📦 Installing Python dependencies..."
pip install -q -r "$ROOT/requirements.txt"

# ── React build ────────────────────────────────────────────────────────────────
if [ ! -d "$ROOT/frontend/dist" ]; then
  echo "🏗  Building React frontend..."
  cd "$ROOT/frontend"
  npm install --prefer-offline
  npm run build
  cd "$ROOT"
else
  echo "✅ React build found (frontend/dist). Skipping rebuild."
  echo "   To force rebuild: rm -rf frontend/dist && ./start.sh"
fi

# ── Start server ───────────────────────────────────────────────────────────────
mkdir -p "$ROOT/logs" "$ROOT/data"
PORT="${PORT:-8000}"
echo ""
echo "🚀 Starting WholesaleOS on http://localhost:$PORT"
echo "   Legacy pipeline UI: http://localhost:$PORT/v1"
echo "   Press Ctrl+C to stop."
echo ""
cd "$ROOT"
exec uvicorn web.app:app --host 0.0.0.0 --port "$PORT"
