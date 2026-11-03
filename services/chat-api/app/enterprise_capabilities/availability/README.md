# Built-in tool availability

The runtime composition root injects one dependency policy into profile compilation
and invocation. A profile excludes unavailable capabilities. Invocation rechecks
state because connections, permissions and model settings can change after publication.
Unknown capabilities are excluded until their admission policy is registered.

| Capability group | Admission |
| --- | --- |
| Browser task | Current user's connected local browser agent |
| Image generation | Same tenant and user model selection as image execution |
| Vision facts | Multimodal enabled and authorized active vision model |
| Search / progressive research | Same configured provider router as execution; check once per profile |
| Built-in presentations | Enabled switch and all configured models valid |
| Code execution | Local restricted backend, or authenticated manager readiness including execution image |
| Knowledge search | Internal retrieval service configured and healthy; external source tool active and authorized |
| SkillHub installation | Configured valid endpoint |
| Document read / parse / resource extraction / PDF editing / annotation | Bundled local implementations and fallbacks; validate source permissions and formats at invocation |
| Metrics / spreadsheet / artifact export | Bundled processing; format-specific validation at invocation |
| Content production / translation / form filling | Inherit the selected conversation model; validated by runtime execution context |
| Web collection | Direct HTTP with optional provider fallback; no API key required |

Independent checks run concurrently, each bounded to 1.5 seconds. HTTP readiness probes have a 700 ms timeout;
there are no cross-user caches and no model generation or paid search probes.
Known unavailable dependencies fail closed without blocking unrelated tools. This
is a current configuration/readiness snapshot, not a guarantee against a later
network outage, revoked credential or error in Agent-generated arguments/code.

Failure telemetry remains unchanged. UI code-attempt labels categorize recognized
Python errors; raw errors stay available in technical details. A completed task
with earlier failed attempts is distinct from a failed task. No retry is claimed
unless the execution timeline contains one.
