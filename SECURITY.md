# Security Policy

Please do not disclose suspected vulnerabilities in public issues. Use GitHub's
private vulnerability reporting feature for this repository. If that feature is
not available, contact a maintainer privately before sharing details. Include
the affected commit or release, impact, reproduction steps and any suggested
mitigation, but never include real credentials or customer data.

Self-hosted operators are responsible for TLS termination, network access
controls, backups, and rotating every credential used by their deployment.
Never reuse values from example environment files in production. The Docker
Compose bootstrap generates deployment-specific application secrets and keeps
them in a persistent Docker volume.

Security fixes are provided for the current release line. Older releases may
require upgrading before a fix can be applied.
