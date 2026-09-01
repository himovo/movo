# Contributing to MOVO

Contributions should be focused, modular, and covered by tests appropriate to
the change. Do not commit environment files, credentials, generated build
caches, uploaded documents, avatars, logs, or other runtime data.

Before opening a pull request, run the relevant checks:

```bash
python scripts/check_open_source_hygiene.py
python -m compileall -q services/chat-api/app services/admin-api/app services/document-parser/app
cd apps/user-web && npm run build
cd ../admin-web && npm run build
```

Describe the user-visible behavior, migration impact, verification performed,
and any configuration changes. Keep new capabilities in focused modules rather
than extending already-large endpoint or UI files.
