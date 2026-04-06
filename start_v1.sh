#!/bin/bash

# --- CONFIGURATIE ---
PROJECT_ROOT="/Users/gvangalen/Antigravity-Trading-Tool"
BACKEND_DIR="$PROJECT_ROOT/backend/trading-tool-backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend/trading-tool-frontend"

echo "🚀 Starten van Antigravity Trading Tool V1..."

# 1. Controleer PostgreSQL
echo "🐘 Controleren van PostgreSQL..."
if pg_isready -h 127.0.0.1 -p 5432 > /dev/null 2>&1; then
    echo "✅ PostgreSQL draait al."
else
    echo "🔄 PostgreSQL starten via Homebrew..."
    brew services start postgresql@14
    sleep 2
fi

# 2. Start Backend
echo "📡 Backend opstarten (FastAPI)..."
cd "$BACKEND_DIR"
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload > "$PROJECT_ROOT/backend.log" 2>&1 &
BACKEND_PID=$!
echo "✅ Backend gestart (PID: $BACKEND_PID). Logs: backend.log"

# 3. Start Frontend
echo "💻 Frontend opstarten (Next.js)..."
cd "$FRONTEND_DIR"
npm run dev > "$PROJECT_ROOT/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "✅ Frontend gestart (PID: $FRONTEND_PID). Logs: frontend.log"

echo ""
echo "--------------------------------------------------"
echo "🌐 Omgeving is online!"
echo "📍 Backend: http://localhost:8000/api/health"
echo "📍 Frontend: http://localhost:3000"
echo "--------------------------------------------------"
echo "💡 Gebruik 'pkill -f uvicorn' en 'pkill -f next-server' om alles te stoppen."
