#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_WEB_DIR="$ROOT_DIR/apps/user-web"
CHAT_API_DIR="$ROOT_DIR/services/chat-api"
ADMIN_WEB_DIR="$ROOT_DIR/apps/admin-web"
ADMIN_API_DIR="$ROOT_DIR/services/admin-api"
DOCUMENT_PARSER_DIR="$ROOT_DIR/services/document-parser"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
ADMIN_API_PORT="${ADMIN_API_PORT:-8100}"
ADMIN_WEB_PORT="${ADMIN_WEB_PORT:-3100}"
DOC_PROCESSING_PORT="${DOC_PROCESSING_PORT:-8200}"
ASKAI_REDIS_URL="${ASKAI_REDIS_URL:-redis://127.0.0.1:6379/0}"
BACKEND_PYTHON_BIN=""
DOC_PROCESSING_PYTHON_BIN=""

kill_port() {
    local port="$1"
    local pids
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
    if [ -n "$pids" ]; then
        echo "Releasing port :$port ..."
        kill $pids 2>/dev/null || true
        sleep 1
        pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
        if [ -n "$pids" ]; then
            kill -9 $pids 2>/dev/null || true
        fi
    fi
}

cleanup_ports() {
    kill_port "$BACKEND_PORT"
    kill_port "$FRONTEND_PORT"
    kill_port "$ADMIN_API_PORT"
    kill_port "$ADMIN_WEB_PORT"
    kill_port "$DOC_PROCESSING_PORT"
}

ensure_redis() {
    if ! command -v redis-cli >/dev/null 2>&1; then
        echo "Redis CLI not found. Install Redis first: brew install redis && brew services start redis"
        exit 1
    fi
    if ! redis-cli -u "$ASKAI_REDIS_URL" ping >/dev/null 2>&1; then
        echo "Redis is not available at $ASKAI_REDIS_URL"
        echo "Start Redis first: brew services start redis"
        exit 1
    fi
}

cleanup() {
    echo ""
    echo "Stopping services..."
    kill $(jobs -p) 2>/dev/null || true
    cleanup_ports
    exit
}

trap cleanup SIGINT SIGTERM

ensure_backend_venv() {
    cd "$CHAT_API_DIR"
    : > backend.log
    if [ -d "venv" ]; then
        source venv/bin/activate
    else
        python -m venv venv
        source venv/bin/activate
    fi
    export PATH="$(pwd)/venv/bin:$PATH"
    export PYTHONUTF8=1
    export PYTHONIOENCODING=utf-8
    export LANG="${LANG:-en_US.UTF-8}"
    export LC_ALL="${LC_ALL:-en_US.UTF-8}"
    export ASKAI_ADMIN_APP_ENV="${ASKAI_ADMIN_APP_ENV:-development}"
    export ASKAI_ADMIN_DOCUMENT_PROCESSING_BASE_URL="${ASKAI_ADMIN_DOCUMENT_PROCESSING_BASE_URL:-http://127.0.0.1:$DOC_PROCESSING_PORT}"
    export ASKAI_ADMIN_ADMIN_API_PUBLIC_BASE_URL="${ASKAI_ADMIN_ADMIN_API_PUBLIC_BASE_URL:-http://127.0.0.1:$ADMIN_API_PORT}"
    export ASKAI_DOC_PROCESSING_REDIS_URL="${ASKAI_DOC_PROCESSING_REDIS_URL:-$ASKAI_REDIS_URL}"
    BACKEND_PYTHON_BIN="$(pwd)/venv/bin/python"
    cd "$ROOT_DIR"
}

ensure_document_processing_venv() {
    cd "$DOCUMENT_PARSER_DIR"
    if [ -d ".venv" ]; then
        :
    else
        "$BACKEND_PYTHON_BIN" -m venv .venv
    fi
    DOC_PROCESSING_PYTHON_BIN="$(pwd)/.venv/bin/python"
    if ! "$DOC_PROCESSING_PYTHON_BIN" -c "import celery, fastapi, oss2, pymongo, pydantic_settings, redis, uvicorn" >/dev/null 2>&1; then
        "$DOC_PROCESSING_PYTHON_BIN" -m pip install -r requirements.txt
    fi
    cd "$ROOT_DIR"
}

start_runtime_backend() {
    echo "Starting Backend on :$BACKEND_PORT ..."
    cd "$CHAT_API_DIR"
    PYTHONPATH="$(pwd)" "$BACKEND_PYTHON_BIN" -m uvicorn app.main:app --reload --reload-dir app --port "$BACKEND_PORT" \
        --timeout-graceful-shutdown "${BACKEND_GRACEFUL_SHUTDOWN_SECONDS:-5}" \
        --reload-exclude "backend.log" \
        --reload-exclude "static/*" \
        --reload-exclude "*.pyc" \
        --reload-exclude "__pycache__/*" &
    cd "$ROOT_DIR"
}

start_frontend() {
    echo "Starting Frontend on :$FRONTEND_PORT ..."
    cd "$USER_WEB_DIR"
    npm run dev &
    cd "$ROOT_DIR"
}

start_admin_api() {
    echo "Starting Admin API on :$ADMIN_API_PORT ..."
    cd "$ADMIN_API_DIR"
    PYTHONPATH="$(pwd)" "$BACKEND_PYTHON_BIN" -m uvicorn app.main:app --reload --reload-dir app --port "$ADMIN_API_PORT" &
    cd "$ROOT_DIR"
}

start_document_processing_service() {
    echo "Starting Document Processing Service on :$DOC_PROCESSING_PORT ..."
    cd "$DOCUMENT_PARSER_DIR"
    PYTHONPATH="$(pwd)" "$DOC_PROCESSING_PYTHON_BIN" -m uvicorn app.main:app --reload --reload-dir app --port "$DOC_PROCESSING_PORT" &
    cd "$ROOT_DIR"
}

start_document_worker() {
    echo "Starting Document Worker ..."
    cd "$DOCUMENT_PARSER_DIR"
    PYTHONPATH="$(pwd)" "$DOC_PROCESSING_PYTHON_BIN" -m celery -A app.workers.celery_app:celery_app worker \
        --loglevel=info \
        --queues="${ASKAI_DOC_PROCESSING_CELERY_QUEUE:-document_processing}" &
    cd "$ROOT_DIR"
}

start_admin_web() {
    echo "Starting Admin Web on :$ADMIN_WEB_PORT ..."
    cd "$ADMIN_WEB_DIR"
    npm run dev &
    cd "$ROOT_DIR"
}

echo "Starting AskAI Platform..."
cleanup_ports
ensure_backend_venv
ensure_document_processing_venv
ensure_redis
echo "Using Backend Python: $BACKEND_PYTHON_BIN"
echo "Using Doc Processing Python: $DOC_PROCESSING_PYTHON_BIN"

start_runtime_backend
start_frontend
start_admin_api
start_document_processing_service
start_document_worker
start_admin_web

echo ""
echo "Services are starting up!"
echo "  - Frontend:    http://localhost:$FRONTEND_PORT"
echo "  - Backend:     http://localhost:$BACKEND_PORT/docs"
echo "  - Admin Web:   http://localhost:$ADMIN_WEB_PORT"
echo "  - Admin API:   http://localhost:$ADMIN_API_PORT/docs"
echo "  - Doc Process: http://localhost:$DOC_PROCESSING_PORT/docs"
echo "  - Redis:       $ASKAI_REDIS_URL"
echo ""
echo "Press Ctrl+C to stop all services."

wait
