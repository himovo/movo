#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST_DIR="$ROOT_DIR/services/chat-api/dsh/runtime-host"
HOST_ENTRY="$HOST_DIR/src/host.mjs"
DESKTOP_DIR="$ROOT_DIR/apps/desktop-electron"
DSH_PORT="${DSH_PORT:-8101}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
DSH_STORAGE_ROOT="${DSH_STORAGE_ROOT:-$ROOT_DIR/services/chat-api/dsh/storage}"
DSH_LOG_PATH="${DSH_LOG_PATH:-$ROOT_DIR/services/chat-api/dsh/runtime-host.log}"
PLATFORM_PID=""
DSH_PID=""
DESKTOP_PID=""
START_DESKTOP=false

if [ "${1:-}" = "--desktop" ]; then
    START_DESKTOP=true
elif [ -n "${1:-}" ]; then
    echo "Usage: ./dev_dsh.sh [--desktop]"
    exit 2
fi

find_node() {
    local candidate
    for candidate in \
        "$(command -v node 2>/dev/null || true)" \
        "/Users/jack/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            local major
            major="$($candidate --version | sed 's/^v//' | cut -d. -f1)"
            if [ "$major" -ge 22 ] 2>/dev/null; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

find_pnpm() {
    local candidate
    for candidate in \
        "$(command -v pnpm 2>/dev/null || true)" \
        "/Users/jack/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

kill_port() {
    local pids
    pids="$(lsof -ti tcp:"$DSH_PORT" 2>/dev/null || true)"
    if [ -n "$pids" ]; then
        echo "Releasing DSH port :$DSH_PORT ..."
        kill $pids 2>/dev/null || true
    fi
}

cleanup() {
    trap - SIGINT SIGTERM EXIT
    echo ""
    echo "Stopping ASKAI DSH development stack..."
    if [ -n "$DESKTOP_PID" ]; then
        kill "$DESKTOP_PID" 2>/dev/null || true
        wait "$DESKTOP_PID" 2>/dev/null || true
    fi
    if [ -n "$PLATFORM_PID" ]; then
        kill "$PLATFORM_PID" 2>/dev/null || true
        wait "$PLATFORM_PID" 2>/dev/null || true
    fi
    if [ -n "$DSH_PID" ]; then
        kill "$DSH_PID" 2>/dev/null || true
        wait "$DSH_PID" 2>/dev/null || true
    fi
    kill_port
}

trap cleanup SIGINT SIGTERM EXIT

NODE_BIN="$(find_node || true)"
if [ -z "$NODE_BIN" ]; then
    echo "Node.js 22.19+ or 24+ is required by the pinned DSH runtime."
    exit 1
fi

PNPM_BIN="$(find_pnpm || true)"
if [ -z "$PNPM_BIN" ]; then
    echo "pnpm is required to install the pinned DSH runtime dependencies."
    exit 1
fi

if [ ! -d "$HOST_DIR/node_modules" ]; then
    echo "Installing pinned DSH Runtime Host dependencies..."
    cd "$HOST_DIR"
    PATH="$(dirname "$NODE_BIN"):$PATH" "$PNPM_BIN" install --frozen-lockfile
    cd "$ROOT_DIR"
fi

kill_port
mkdir -p "$DSH_STORAGE_ROOT"
: > "$DSH_LOG_PATH"

export DSH_RUNTIME_HOST_URL="http://127.0.0.1:$DSH_PORT"
export DSH_MODEL_GATEWAY_URL="http://127.0.0.1:$BACKEND_PORT/internal/dsh/model/generate"
export DSH_TOOL_GATEWAY_URL="http://127.0.0.1:$BACKEND_PORT/internal/dsh/tools"
export DSH_MODEL_GATEWAY_SIGNING_SECRET="${DSH_MODEL_GATEWAY_SIGNING_SECRET:-askai-dsh-local-development-signing-secret}"

echo "Starting pinned DSH Runtime Host on :$DSH_PORT ..."
"$NODE_BIN" "$HOST_ENTRY" \
    --host 127.0.0.1 \
    --port "$DSH_PORT" \
    --storage-root "$DSH_STORAGE_ROOT" \
    >> "$DSH_LOG_PATH" 2>&1 &
DSH_PID=$!

for _ in $(seq 1 100); do
    if curl -fsS "http://127.0.0.1:$DSH_PORT/health" >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$DSH_PID" 2>/dev/null; then
        echo "DSH Runtime Host exited during startup. See $DSH_LOG_PATH"
        exit 1
    fi
    sleep 0.1
done

if ! curl -fsS "http://127.0.0.1:$DSH_PORT/health" >/dev/null 2>&1; then
    echo "DSH Runtime Host did not become healthy. See $DSH_LOG_PATH"
    exit 1
fi

echo "DSH Runtime Host is healthy: http://127.0.0.1:$DSH_PORT/health"
cd "$ROOT_DIR"
./dev.sh &
PLATFORM_PID=$!
if [ "$START_DESKTOP" = true ]; then
    echo "Starting Electron desktop after the Web development server is ready..."
    cd "$DESKTOP_DIR"
    npm run dev &
    DESKTOP_PID=$!
    cd "$ROOT_DIR"
fi
wait "$PLATFORM_PID"
