# MOVO Multi-Agent Platform

> A specialized multi-agent platform for complex tasks.
> **Version**: MVP 0.1.0

## Directory Structure

- `apps/user-web/`: Vue 3 + Vite user-facing application
- `apps/admin-web/`: Vue 3 + Vite admin application
- `apps/desktop-electron/`: Electron desktop shell with embedded Chromium
- `apps/local-browser-agent/`: native-CDP desktop browser automation sidecar
- `services/chat-api/`: Python FastAPI service (Agent Runtime)
- `services/admin-api/`: Python FastAPI admin/control-plane service
- `services/document-parser/`: document parsing and preview service
- `docs/`: Requirements and Architecture documentation

## Quick Start (Dev)

### Prerequisites
- Docker & Docker Compose
- Python 3.10+ (for local logic dev)
- Node.js 20+ (for local UI dev)

## Self-Hosted Quick Start

Only Docker and Docker Compose v2 are required. From the repository root run:

```bash
chmod +x movo
./movo up
```

The launcher displays the MOVO logo, starts the complete Compose stack, waits for
the deployment checks, and prints the browser setup address:

```text
http://localhost:3000/admin/setup
```

Complete the organization, initial accounts, and default model connection test
in the browser. Credentials are encrypted before storage. The completion page
then shows the employee Web, admin portal, and desktop enterprise-service
addresses.

Useful commands:

```bash
./movo status
./movo logs chat-api
./movo restart
./movo down       # Stops containers and preserves data volumes
```

The CLI always uses English by default, regardless of the operating-system
language. Chinese can be selected explicitly with `--lang` or `MOVO_LANG`:

```bash
./movo --lang en up
./movo --lang zh-CN up
MOVO_LANG=zh-CN ./movo down
```

The native command remains supported:

```bash
docker compose up -d
```

For a public domain, copy `.env.example` to `.env` and configure
`PUBLIC_BASE_URL=https://ai.company.com` before startup. DNS, HTTPS certificates,
and the external reverse proxy remain deployment-environment responsibilities.

### Quick Start (Local Development)

Since you prefer local development, here is how to start the platform without Docker.

#### 0. One-Click Startup (Recommended)
You can start both backend and frontend with a single command:
```bash
./dev.sh
```

#### 1. Start Backend

**Option A: Using Standard Pip (Recommended)**
```bash
cd services/chat-api
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Option B: Using Poetry (Compatibility metadata)**
```bash
cd services/chat-api
poetry install
poetry run uvicorn app.main:app --reload --port 8000
```

#### 2. Start Frontend
Open a new terminal:
```bash
cd apps/user-web
npm install
npm run dev
```

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000/docs

#### 3. Start Electron Desktop
```bash
cd apps/desktop-electron
npm install
npm run dev
```

### Backend Logging

The backend uses structured request-aware logging. `backend.log` is local-only
and is written only when enabled in `services/chat-api/.env`:

```env
LOG_LEVEL=INFO
LOG_FILE_ENABLED=true
LOG_FILE_PATH=backend.log
LOG_FILE_FORMAT=json
LOG_CONSOLE_PRETTY=true
LOG_DEBUG_PAYLOADS=false
```

Useful lookups:

```bash
grep '"request_id":"<id>"' services/chat-api/backend.log
grep '"session_id":"<id>"' services/chat-api/backend.log
grep '"event":"request.heartbeat"' services/chat-api/backend.log
grep '"level":"ERROR"' services/chat-api/backend.log
```

Large debug payloads are not written to the main log by default. When
`LOG_DEBUG_PAYLOADS=true`, payloads are written under
`services/chat-api/static/debug_snapshots/...` and the log records the artifact path.

## Backend Docker Image

Build and push the backend production image for the test cluster:

```bash
./services/chat-api/scripts/build_push_image.sh
```

Optional overrides:

```bash
REGISTRY=ghcr.io/your-org IMAGE_NAME=movo-backend IMAGE_TAG=latest PUSH=true ./services/chat-api/scripts/build_push_image.sh
```
