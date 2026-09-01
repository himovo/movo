# DSH compatibility policy

ASKAI treats the npm tarball as the deployable identity and the upstream Git
commit as a separately reviewed source snapshot. DeepSeek currently publishes
no Git tag or npm `gitHead` that proves these two artifacts correspond.

| Item | Active baseline | Status | Upgrade rule |
|---|---|---|---|
| Reviewed upstream source | `47f943859bef60e4160492346772ded9b24f765a` (`0.1.0-rc.5`) | reviewed | review upstream diff again |
| Deployable npm train | `@deepseek-ai/dsh@0.1.1-rc.2` | approved, integrity pinned | never use a range |
| Source/package mapping | unavailable upstream | unverified | do not claim correspondence |
| Node platform | `^22.19.0 || >=24.0.0` | required by reviewed source | test every supported deployment image |
| AgentKernel Contract | `askai.agent-kernel.v1` | frozen | incompatible DSH changes stay behind the gateway |
| Kernel Event | `askai.kernel-event.v1` | frozen | add a new contract version; do not mutate v1 |
| Python SDK / stdio | not a product boundary | prohibited | Runtime Host and plugin contract only |
| DSH Core fork | none | prohibited | upstream package stays replaceable |

Every DSH upgrade must pass supply-chain verification, DSH native plugin smoke
tests, AgentKernel contract tests, event replay tests, data isolation tests and
the performance gates in the migration plan. Only `services/chat-api/dsh/` and
the compatibility side of `app/dsh_runtime/` may need a DSH-specific change.

Before changing the pinned release, run the isolated candidate evaluator documented
in `docs/dsh-upgrade-evaluation.md`. A candidate report may set `contract_ready`,
but only the existing full application, platform matrix, packaged smoke and supply-
chain admission gates may establish release readiness.

The previous `0.1.0-rc.6` train remains a documented rollback target. It is not
accepted as the active Runtime Host handshake version and must not coexist with
the active train inside one installed dependency graph.
