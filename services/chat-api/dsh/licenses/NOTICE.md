# DSH dependency evidence

- Upstream: <https://github.com/deepseek-ai/deepseek-harness>
- Reviewed source commit: `0a53fb55bea101816fa226bb964ae2bed71c343b`
- Reviewed source root version: `0.1.2-alpha.2`
- Approved npm release train: `0.1.2-alpha.2`
- License: MIT; vendored text is in `DEEPSEEK-HARNESS-MIT.txt`
- Upstream `THIRD_PARTY_NOTICES.md` SHA256 at the reviewed commit:
  `61f68731049dbea19ba91ad8cf363dd2778c5f7b1f9a63496a6a62c1129eefee`

The exact direct artifacts, registry integrity values and license evidence are
recorded in `../versions.lock`. The complete installed `pnpm-lock.yaml`
dependency graph is represented by the checked-in CycloneDX inventory at
`../sbom.cdx.json`.

The npm `0.1.2-alpha.2` metadata does not publish a verified source mapping.
MOVO therefore treats the npm integrity hash as the deployable artifact
identity and the Git commit as a separate reviewed-source baseline. They must
not be claimed as a verified source/binary correspondence without new upstream
evidence.
