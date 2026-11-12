# DSH dependency evidence

- Upstream: <https://github.com/deepseek-ai/deepseek-harness>
- Reviewed source commit: `ddac96760b6edf8fa0fe17cbdcf0b512f4c12b2c`
- Reviewed source root version: `0.2.2-rc.2`
- Approved npm release train: `0.2.2-rc.2`
- License: MIT; vendored text is in `DEEPSEEK-HARNESS-MIT.txt`
- Upstream `THIRD_PARTY_NOTICES.md` SHA256 at the reviewed commit:
  `4bd8832885ca31daf3e480fb950b9e849446438c0089b05fab67d6c2673fa2ef`

The exact direct artifacts, registry integrity values and license evidence are
recorded in `../versions.lock`. The complete installed `pnpm-lock.yaml`
dependency graph is represented by the checked-in CycloneDX inventory at
`../sbom.cdx.json`.

The npm `0.2.2-rc.2` metadata does not publish a verified source mapping.
MOVO therefore treats the npm integrity hash as the deployable artifact
identity and the Git commit as a separate reviewed-source baseline. They must
not be claimed as a verified source/binary correspondence without new upstream
evidence.
