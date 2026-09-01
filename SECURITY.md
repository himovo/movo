# Security Policy

Please do not disclose suspected vulnerabilities in public issues. Report them
privately to the project maintainers and include the affected version, impact,
reproduction steps, and any suggested mitigation.

Self-hosted operators are responsible for TLS termination, network access
controls, backups, and rotating every credential used by their deployment.
Never reuse values from example environment files in production. The Docker
Compose bootstrap generates deployment-specific application secrets and keeps
them in a persistent Docker volume.

Security fixes are provided for the current release line. Older releases may
require upgrading before a fix can be applied.
