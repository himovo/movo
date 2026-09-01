# DSH dependency evidence

- Upstream: <https://github.com/deepseek-ai/deepseek-harness>
- Reviewed source commit: `47f943859bef60e4160492346772ded9b24f765a`
- Approved npm release train: `0.1.1-rc.2`
- License: MIT; vendored text is in `DEEPSEEK-HARNESS-MIT.txt`
- Upstream `THIRD_PARTY_NOTICES.md` SHA256 at the reviewed commit:
  `61f68731049dbea19ba91ad8cf363dd2778c5f7b1f9a63496a6a62c1129eefee`

The full third-party notice file is not copied in step 1 because no DSH
runtime artifact is bundled yet. Step 2 must generate an SBOM and include the
notices belonging to the exact installed `pnpm-lock.yaml` dependency graph.

The npm `0.1.1-rc.2` metadata does not publish a verified source mapping, and the upstream
repository currently has no matching public tag. ASKAI therefore treats the
npm integrity hash as the deployable artifact identity and the Git commit as
a separate reviewed-source baseline. They must not be claimed as a verified
source/binary correspondence without new upstream evidence.
