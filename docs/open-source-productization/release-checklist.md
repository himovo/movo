# MOVO Community Repository Release Checklist

## Legal and public identity

- [x] LICENSE and NOTICE identify 北京果然智汇科技有限公司 as the legal
      copyright owner.
- [x] Security, commercial licensing and support use `support@himovo.com`.
- [ ] Review the MOVO logo and every bundled third-party asset for distribution rights.
- [x] Confirm that release messaging says “source-available” rather than claiming
      an unmodified OSI-approved Apache 2.0 license.

## Repository boundary

- [x] No desktop client, local browser sidecar, official website, CRM example or
      cloud/enterprise overlay source is tracked.
- [x] No environment file, credential, runtime data, generated output or customer material is tracked.
- [x] The open-source hygiene script passes.
- [ ] Rotate every credential from the local ignored `.env` files that was exposed
      to a review tool or copied from an existing deployment before publication.
- [x] DSH lock, compatibility matrix, SBOM and DSH notice are current.
- [ ] Complete the legal review of transitive third-party license obligations.

## Build and runtime

- [x] Both Web production builds pass.
- [x] Python services compile and relevant tests pass.
- [x] DSH Runtime Host installs from its lock and its contract suite passes.
- [x] Docker Compose pull and source-build configurations validate.
- [x] Every first-run Docker image builds without private registries or credentials.
- [x] A clean deployment reaches healthy state and completes initial setup.
- [x] The setup organization is community, billing is disabled and member limit is unlimited.
- [x] GHCR release images are available for both amd64 and arm64.
- [ ] Backup, upgrade and rollback steps have been exercised on non-production data.

## GitHub publication

- [x] The GitHub repository is public.
- [x] The repository contains only the intended new MOVO history.
- [x] Branch protection requires the always-on runtime and Web build guards;
      path-specific DSH guards run whenever their protected sources change.
- [x] Private vulnerability reporting and Discussions are enabled.
- [x] Issue labels and templates are available.
- [x] The release tag, changelog and approved component image set identify the
      same release version.
- [x] All published `movo-*` GHCR packages are public and anonymously pullable.
- [x] Git remotes were reviewed before the initial public push.
