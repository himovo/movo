# MOVO Community Edition

MOVO is a goal-driven agent platform for enterprise tasks. Users describe the
desired result; MOVO plans the work, invokes models and tools, processes
documents, requests approval for risky actions, and returns traceable outputs.

This repository contains the self-hosted Community Edition. It is the shared
source foundation used by MOVO cloud and future enterprise distributions.

## Included components

| Path | Component |
|---|---|
| `apps/user-web/` | Vue 3 user workspace |
| `apps/admin-web/` | Vue 3 setup and administration console |
| `services/chat-api/` | FastAPI conversation, task, Agent, Skill and DSH gateway |
| `services/chat-api/dsh/runtime-host/` | Node.js DSH Runtime Host |
| `services/admin-api/` | FastAPI organization, user, model and platform management API |
| `services/document-parser/` | Document parsing, preview, retrieval API and worker |
| `deploy/` | Bootstrap and gateway configuration |

The proprietary desktop client, local browser sidecar, official website and
commercial CRM examples are not included in this repository.

## Community Edition behavior

A tenant created by the self-hosted setup flow is marked as `community`:

- no member-count limit;
- billing is disabled;
- self-managed model connections are enabled;
- data and runtime services remain in the operator's deployment.

Cloud plan limits are not used to determine Community Edition entitlements.

## Quick start

### Requirements

- Docker Desktop, or Docker Engine with Docker Compose v2
- at least 8 GB of available memory; document-model image construction may
  require more during the first build

Clone the repository and run:

```bash
chmod +x movo
./movo up
```

MOVO waits for the deployment health checks and prints the setup URL:

```text
http://localhost:3000/admin/setup
```

The first build downloads Node, Python, Playwright, LibreOffice, Docling and
model dependencies and can take several minutes. Later starts reuse Docker
images and caches.

Useful commands:

```bash
./movo status
./movo logs chat-api
./movo restart
./movo down       # Preserve data volumes
./movo down -v    # Permanently remove MOVO data volumes
```

To use a different port or public URL:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
MOVO_PORT=3000
MOVO_VOLUME_PREFIX=movo
PUBLIC_BASE_URL=https://movo.example.com
```

Persistent Docker volumes use the `movo_` prefix by default. Keep
`MOVO_VOLUME_PREFIX` stable after the first startup. Existing AskAI volumes
are not reused or removed automatically.

TLS certificates, DNS and the external reverse proxy remain the deployment
operator's responsibility.

## Services

The default Compose deployment contains 12 services:

- gateway, user-web and admin-web;
- chat-api and dsh-runtime-host;
- admin-api;
- document-api and document-worker;
- mongo, redis and weaviate;
- one-time bootstrap secret initialization.

MongoDB, Redis, Weaviate, generated files, document data, DSH state and
deployment secrets are stored in independent `movo_*` Docker volumes.

## Local development

The Docker deployment is the supported full-stack path. For focused local
development, install only the dependencies for the component being changed.

```bash
# Chat API
cd services/chat-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# User Web
cd apps/user-web
npm ci
npm run dev

# Admin Web
cd apps/admin-web
npm ci --legacy-peer-deps
npm run dev
```

## Verification

Before publishing or submitting a change, run the relevant checks:

```bash
python3 scripts/check_open_source_hygiene.py
python3 -m compileall -q services/chat-api/app services/admin-api/app services/document-parser/app
docker compose config --quiet
```

The production frontends and services can be verified with:

```bash
docker compose build user-web admin-web dsh-runtime-host
docker compose build chat-api admin-api document-api document-worker
```

## Documentation and support

- Product direction and deployment decisions: `docs/open-source-productization/`
- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security policy: [SECURITY.md](SECURITY.md)
- Community support policy: [SUPPORT.md](SUPPORT.md)

## License

MOVO is source-available under the [MOVO Community License](LICENSE), based on
Apache License 2.0 with additional conditions. Without written authorization,
the license does not permit operating a hosted multi-tenant SaaS offering or
removing/modifying the MOVO logo and copyright notices in the included
frontends.

These additional restrictions mean that the MOVO Community License is not the
unmodified Apache License 2.0 and should not be represented as an OSI-approved
open-source license.
