# Contributing to MOVO

Contributions should be focused, modular, and covered by tests appropriate to
the change. Do not commit environment files, credentials, generated build
caches, uploaded documents, avatars, logs, or other runtime data.

By intentionally submitting a contribution, you agree to the contribution
terms in LICENSE, including use of the contribution in MOVO commercial products
and services. Do not submit code or assets that you do not have the right to
license under those terms.

Before opening a pull request, run the relevant checks:

```bash
python3 scripts/check_open_source_hygiene.py
python -m compileall -q services/chat-api/app services/admin-api/app services/document-parser/app
cd apps/user-web && npm run build
cd ../admin-web && npm ci --legacy-peer-deps && npm run build
```

Describe the user-visible behavior, migration impact, verification performed,
and any configuration changes. Keep new capabilities in focused modules rather
than extending already-large endpoint or UI files.

Use the pull request template and explicitly identify changes to public APIs,
stored data, environment variables, deployment topology or licensing. Security
vulnerabilities must follow SECURITY.md and must not be filed publicly.
