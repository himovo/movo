# MOVO Community Repository Release Checklist

## Legal and public identity

- [ ] Replace “MOVO” in LICENSE and NOTICE with the legal copyright owner.
- [ ] Confirm the commercial-license and security contact channels.
- [ ] Review the MOVO logo and every bundled third-party asset for distribution rights.
- [ ] Confirm that release messaging says “source-available” rather than claiming
      an unmodified OSI-approved Apache 2.0 license.

## Repository boundary

- [ ] No desktop client, local browser sidecar, official website, CRM example or
      cloud/enterprise overlay source is tracked.
- [ ] No environment file, credential, runtime data, generated output or customer material is tracked.
- [ ] The open-source hygiene script passes.
- [ ] DSH lock, compatibility matrix, SBOM and third-party notices are current.

## Build and runtime

- [ ] Both Web production builds pass.
- [ ] Python services compile and relevant tests pass.
- [ ] DSH Runtime Host installs from its lock and its contract suite passes.
- [ ] Docker Compose configuration validation passes.
- [ ] Every first-run Docker image builds without private registries or credentials.
- [ ] A clean deployment reaches healthy state and completes initial setup.
- [ ] The setup organization is community, billing is disabled and member limit is unlimited.
- [ ] Backup, upgrade and rollback steps have been exercised on non-production data.

## GitHub publication

- [ ] The repository contains only the intended new MOVO history.
- [ ] Branch protection requires the runtime and Web build guards.
- [ ] Private vulnerability reporting and Discussions are enabled.
- [ ] Issue labels and templates are available.
- [ ] The release tag, image tags and changelog identify the same commit.
- [ ] No Git remote is added or pushed until all items above are accepted.
