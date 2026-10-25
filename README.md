<p align="center">
  <img src="apps/user-web/public/movo-logo.png" alt="MOVO" width="180">
</p>

<h1 align="center">MOVO Community Edition</h1>

<p align="center">
  A self-hosted enterprise Agent platform built on DeepSeek Harness (DSH).
</p>

<p align="center">
  <strong>English</strong> · <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="#start-in-5-minutes"><strong>🚀 Quick Start</strong></a> ·
  <a href="https://movo.oss-cn-beijing.aliyuncs.com/5E22C353-55F1-45AB-B606-0ED16CC99833.mp4"><strong>▶ Watch Demo</strong></a> ·
  <a href="https://www.himovo.com/en/guide/introduction.html"><strong>📘 Documentation</strong></a> ·
  <a href="https://github.com/himovo/movo/releases/latest"><strong>🆕 What's New</strong></a>
</p>

<p align="center">
  <a href="https://github.com/himovo/movo"><img src="https://img.shields.io/github/stars/himovo/movo?style=social" alt="GitHub Stars"></a> · <a href="https://linux.do" alt="LINUX DO"><img src="https://shorturl.at/ggSqS" /></a><br>
  If MOVO is useful to you, click <strong>Star</strong> in the upper-right corner to support the project.
</p>

<br>

MOVO brings DSH Agents from development experiments into enterprise production. It combines the DSH Runtime, Skills, Tools and MCP ecosystem with a deployable user workspace, enterprise knowledge, identity and access control, administration, governance and file delivery.

> **In one sentence:** DSH runs the Agent; MOVO brings the Agent into enterprise production.

<br>

<p align="center">
  <img src="assets/dsh-movo-responsibilities-en.png" alt="How DeepSeek Harness and MOVO divide responsibilities" width="760">
</p>

<br>

This repository contains the self-hosted MOVO Community Edition.

## Start in 5 minutes

With Git and Docker Desktop (or Docker Engine with Docker Compose v2) installed:

```bash
git clone https://github.com/himovo/movo.git
cd movo
chmod +x movo
./movo up
```

Then open:

```text
http://localhost:3000/admin/setup
```

The launcher pulls the official prebuilt images, waits for the services to become healthy and prints the setup address. No `.env` file or local image build is required. Windows users should run MOVO inside an Ubuntu WSL 2 distribution; see the [online quick-start guide](https://www.himovo.com/en/guide/getting-started.html).

For users in mainland China, use `./movo --mirror cn up` to pull both MOVO and its MongoDB, Redis, Weaviate and Alpine images from the public Beijing ACR mirror. The default `./movo up` continues to use GHCR and Docker Hub. Mirror selection is explicit rather than inferred from language or IP address; no `.env` changes are required. Use the same flag with `update` when upgrading. The China mirror supports Linux/amd64 and Linux/arm64; Docker selects the matching image for the host. Source builds remain `./movo up --build` without a mirror flag.

If `.env` pins `MOVO_VERSION`, the same tag must exist in the selected registry. The China mirror initially publishes `latest` and the immutable `candidate-<commit SHA>` tag; it does not automatically contain every GHCR release tag. Back up your data before switching an existing deployment between registries.

> Got MOVO running? Please click **Star** in the upper-right corner. It helps more developers discover the project.

## Product demo

See MOVO in action in the complete product walkthrough:

<p align="center">
  <a href="https://movo.oss-cn-beijing.aliyuncs.com/5E22C353-55F1-45AB-B606-0ED16CC99833.mp4"><strong>▶ Watch the MOVO demo video</strong></a>
</p>

The video opens in your browser and can be played directly without downloading it first.

## Why MOVO

Running an Agent demo is very different from operating an Agent platform for a team. MOVO provides the product and infrastructure layer around DSH so you can move into real use without assembling authentication, knowledge, administration, governance and delivery systems yourself.

- **Stay native to DSH.** Use the official DSH Runtime, Skills, Tools, MCP integrations and sub-agent capabilities instead of adopting a disconnected proprietary runtime.
- **Deploy a complete product.** Start the user workspace, admin console, APIs, document processing, retrieval and infrastructure together with Docker Compose.
- **Keep control of models and data.** Connect your own model providers and keep application data, knowledge and runtime services in your deployment.
- **Serve users as well as developers.** Give employees a usable workspace while administrators manage accounts, models, knowledge, capabilities, quotas and audit records.
- **Grow without rebuilding the foundation.** Begin with the self-hosted Community Edition and retain the same shared source foundation as deployment requirements expand.

If you only need a low-level Agent runtime, DSH may be enough. Choose MOVO when you need to turn that runtime into a deployable, manageable product for real users.

## What MOVO provides

| Capability | What you can do |
| --- | --- |
| DSH-native Agent runtime | Use planning, tool calls, Skills, sub-agents and governed execution through the bundled DSH Runtime Host. |
| Enterprise knowledge and research | Search internal documents and public sources, run multi-round research, retain citations and inspect supporting evidence. |
| Document and multimodal intelligence | Parse PDF, DOCX, XLSX, PPTX, CSV and Markdown files, including images, charts and other visual content. |
| Content and file generation | Create reports, articles, PPTX presentation files, spreadsheets, PDFs and Markdown deliverables. |
| Skills, Tools and MCP | Reuse workflows and connect HTTP or MCP services to business systems. |
| Automation and governance | Schedule tasks, require approval for sensitive tool actions, trace executions and retain generated artifacts. |
| Enterprise administration | Manage organizations, users, roles, models, knowledge, Skills, Tools, audit records and runtime health. |

Typical use cases include enterprise knowledge Q&A, policy and project-material retrieval, multi-source research, competitive analysis, report and presentation generation, spreadsheet processing, translation, template filling and controlled system integration.

## Community Edition

A tenant created by the self-hosted setup flow is marked as `community`:

- no member-count limit;
- billing and commercial plan enforcement are disabled;
- self-managed model connections are enabled;
- data and runtime services remain in your own deployment.

The repository includes the Web user workspace, administration console, conversation and Agent APIs, DSH Runtime Host, document parser and retrieval services, and Docker deployment configuration.

### Browser Agent and Code Agent

The self-hosted Web workspace supports chat, research, knowledge, files and content generation. To use **Browser Agent** or **Code Agent**, install [MOVO Desktop](https://www.himovo.com/en/download.html) and connect it to your self-hosted MOVO service.

MOVO Desktop provides the local browser session, code workspace, project terminal and Git integration required by these capabilities. It is distributed separately as proprietary software; its source code is not included in this repository and is not part of the Community Edition source release.

| Capability | Self-hosted Web | MOVO Desktop |
| --- | :---: | :---: |
| Chat, research and enterprise knowledge | ✓ | ✓ |
| Document understanding and content generation | ✓ | ✓ |
| Browser Agent | — | ✓ |
| Code Agent, local projects, terminal and Git | — | ✓ |
| Requires a self-hosted MOVO service | ✓ | ✓, connects to that service |
| Source included in this repository | ✓ | —, distributed separately |

## Architecture

```mermaid
flowchart LR
    U[User workspace] --> G[Gateway]
    A[Admin console] --> G
    G --> C[Chat API]
    G --> M[Admin API]
    C --> D[DSH Runtime Host]
    C --> P[Document services]
    M --> P
    C --> S[(MongoDB / Redis / Weaviate)]
    M --> S
    P --> S
```

The default Docker Compose deployment starts 12 services: the gateway, two Web applications, three application APIs, the DSH Runtime Host, a document worker, MongoDB, Redis, Weaviate and a one-time secret bootstrap service.

## Deployment and operations

### Requirements and platform notes

- Git
- Docker Desktop, or Docker Engine with Docker Compose v2
- at least 8 GB of available memory
- at least 20 GB of available disk space for images and application data
- network access to the selected image registries during the initial image pull (GHCR/Docker Hub by default, or ACR with `--mirror cn`)
- credentials for at least one compatible model API to complete setup

The quick-start command above works on Linux and macOS. The launcher pulls the selected MOVO and infrastructure images sequentially and keeps retrying network failures until the pull succeeds or the user presses `Ctrl+C`. The first startup downloads several container images and can take some time. Normal users do **not** need to build the images locally.

On Windows, use Docker Desktop with WSL 2 and Ubuntu. Check that Ubuntu exists with `wsl -l -v`, then enter it explicitly with `wsl -d Ubuntu`; do not run MOVO from a prompt beginning with `docker-desktop:`. See the [online setup steps](https://www.himovo.com/en/guide/getting-started.html#windows-enter-ubuntu-not-docker-desktop).

You can also start the default GHCR/Docker Hub images directly with `docker compose up -d`, including from Windows PowerShell or Command Prompt. Neither command requires an `.env` file, but native Compose pulls in parallel and does not provide the launcher's continuous retry loop or readiness wait. For the China mirror, use the `./movo --mirror cn up` launcher command. To build and start local images from source instead, use `./movo up --build`.

Open:

```text
http://localhost:3000/admin/setup
```

The setup wizard checks the deployment and guides you through creating the organization and initial accounts, connecting a default chat model, and optionally configuring embedding, reranking, vision, image generation and Web search providers. Provider credentials are encrypted before storage.

After setup:

| Entry | Default URL | Purpose |
| --- | --- | --- |
| User workspace | `http://localhost:3000/` | Conversations, research, knowledge, files and content generation |
| Admin console | `http://localhost:3000/admin/` | Users, models, knowledge, Skills, Tools and governance |
| Setup wizard | `http://localhost:3000/admin/setup` | First-run initialization only |

### Common operations

```bash
./movo status
./movo logs chat-api
./movo restart
./movo update
./movo fix       # Only for sequence conflicts reported during upgrade; pauses chat
./movo backup /path/on/a/large-disk/movo-backup
./movo down       # Stop containers and preserve data
./movo down -v    # Permanently delete MOVO data after confirmation
```

For production, pin a release tag instead of using `latest`, and back up data before upgrades. See the [online deployment guide](https://www.himovo.com/en/guide/getting-started.html) for setup details.

### Configuration

The default local deployment does not require an `.env` file. To change the public port, canonical URL, image version or volume prefix:

```bash
cp .env.example .env
```

```env
MOVO_PORT=3000
MOVO_VOLUME_PREFIX=movo
MOVO_IMAGE_PREFIX=ghcr.io/himovo/movo
MOVO_VERSION=vX.Y.Z
PUBLIC_BASE_URL=https://movo.example.com
```

Keep `MOVO_VOLUME_PREFIX` stable after first startup. DNS, TLS certificates and the external reverse proxy remain the deployment operator's responsibility.

## Build from source

Building locally is intended for contributors and developers. Build and start
the source tree with:

```bash
./movo up --build
```

To build the images without starting the services:

```bash
./movo build
```

Source builds download Playwright, LibreOffice, Docling and model assets, so they need substantially more time and disk space than the prebuilt-image path.

## Repository layout

| Path | Component |
| --- | --- |
| `apps/user-web/` | Vue 3 user workspace |
| `apps/admin-web/` | Vue 3 setup and administration console |
| `services/chat-api/` | FastAPI conversation, task, Agent, Skill and DSH gateway |
| `services/chat-api/dsh/runtime-host/` | Node.js DSH Runtime Host |
| `services/admin-api/` | FastAPI organization, user, model and platform management API |
| `services/document-parser/` | Document parsing, preview, retrieval API and worker |
| `deploy/` | Bootstrap and gateway configuration |

## Contributing and support

Issues and feature requests are welcome. Clear use cases and reproducible feedback may be implemented quickly when they benefit the wider community. A recent example is the ability to install external Skills directly from ZIP packages.

- [GitHub Discussions](https://github.com/himovo/movo/discussions) for questions, ideas and deployment experience
- [GitHub Issues](https://github.com/himovo/movo/issues) for reproducible bugs
- [Contribution guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Community support policy](SUPPORT.md)
- Security, commercial licensing and support: `support@himovo.com`

Before submitting a change, run the relevant checks described in [CONTRIBUTING.md](CONTRIBUTING.md). At minimum, the repository hygiene check is:

```bash
python3 scripts/check_open_source_hygiene.py
```

## License

MOVO is source-available under the [MOVO Community License](LICENSE), based on Apache License 2.0 with additional conditions. Without written authorization, the license does not permit operating a hosted multi-tenant SaaS offering, removing or modifying the MOVO logo and copyright notices in the included frontends, or selling MOVO or a derivative as an OEM, white-label, or rebranded enterprise Agent platform whose primary product is MOVO itself.

These additional restrictions mean that the MOVO Community License is not the unmodified Apache License 2.0 and should not be represented as an OSI-approved open-source license. For commercial licensing, multi-tenant SaaS authorization, OEM or white-label distribution, or alternative branding rights, contact `support@himovo.com`.
