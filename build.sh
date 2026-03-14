#!/usr/bin/env bash
# PaaS build script — runs once at deploy time on Railway, Render, Fly.io, etc.
# Installs Python deps, then builds the React frontend.
set -euo pipefail

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Installing Node dependencies..."
cd frontend
npm install --prefer-offline

echo "==> Building React frontend..."
# VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set as
# environment variables in your PaaS dashboard — Vite reads them at build time.
npm run build
cd ..

echo "==> Creating runtime directories..."
mkdir -p logs data

echo "==> Build complete."
