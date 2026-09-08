#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=internal_service_auth.sh
source "$SCRIPT_DIR/internal_service_auth.sh"

unset ADMIN_BACKEND_SERVICE_TOKEN ASKAI_ADMIN_BACKEND_SERVICE_TOKEN
movo_prepare_internal_service_auth
test -n "$ADMIN_BACKEND_SERVICE_TOKEN"
test "$ADMIN_BACKEND_SERVICE_TOKEN" = "$ASKAI_ADMIN_BACKEND_SERVICE_TOKEN"

ADMIN_BACKEND_SERVICE_TOKEN="canonical-token"
ASKAI_ADMIN_BACKEND_SERVICE_TOKEN="stale-alias"
movo_prepare_internal_service_auth
test "$ADMIN_BACKEND_SERVICE_TOKEN" = "canonical-token"
test "$ASKAI_ADMIN_BACKEND_SERVICE_TOKEN" = "canonical-token"

unset ADMIN_BACKEND_SERVICE_TOKEN
ASKAI_ADMIN_BACKEND_SERVICE_TOKEN="legacy-token"
movo_prepare_internal_service_auth
test "$ADMIN_BACKEND_SERVICE_TOKEN" = "legacy-token"
test "$ASKAI_ADMIN_BACKEND_SERVICE_TOKEN" = "legacy-token"

echo "internal service auth checks passed"
