#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=internal_service_auth.sh
source "$SCRIPT_DIR/internal_service_auth.sh"

export ASKAI_ADMIN_JWT_SECRET="test-admin-jwt-secret"
unset ADMIN_BACKEND_SERVICE_TOKEN ASKAI_ADMIN_BACKEND_SERVICE_TOKEN \
    MOVO_DOC_PROCESSING_SERVICE_TOKEN ASKAI_ADMIN_DOCUMENT_PROCESSING_SERVICE_TOKEN \
    DOCUMENT_PROCESSING_SERVICE_TOKEN MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET \
    MOVO_DOC_PROCESSING_CALLBACK_TOKEN ASKAI_ADMIN_DOCUMENT_PROCESSING_CALLBACK_TOKEN
movo_prepare_internal_service_auth
test -n "$ADMIN_BACKEND_SERVICE_TOKEN"
test "$ADMIN_BACKEND_SERVICE_TOKEN" = "$ASKAI_ADMIN_BACKEND_SERVICE_TOKEN"
test -n "$MOVO_DOC_PROCESSING_SERVICE_TOKEN"
test "$DOCUMENT_PROCESSING_SERVICE_TOKEN" = "$MOVO_DOC_PROCESSING_SERVICE_TOKEN"
test "$ASKAI_ADMIN_DOCUMENT_PROCESSING_SERVICE_TOKEN" = "$MOVO_DOC_PROCESSING_SERVICE_TOKEN"
test -n "$MOVO_DOC_PROCESSING_CALLBACK_TOKEN"
test "$ASKAI_ADMIN_DOCUMENT_PROCESSING_CALLBACK_TOKEN" = "$MOVO_DOC_PROCESSING_CALLBACK_TOKEN"
test "$MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET" = "$ASKAI_ADMIN_JWT_SECRET"

fixture_root="$(mktemp -d)"
trap 'rm -rf "$fixture_root"' EXIT
mkdir -p "$fixture_root/services/admin-api"
printf '%s\n' 'ASKAI_ADMIN_DOCUMENT_PROCESSING_CALLBACK_TOKEN=persisted-callback-token' > "$fixture_root/services/admin-api/.env"
unset MOVO_DOC_PROCESSING_CALLBACK_TOKEN ASKAI_ADMIN_DOCUMENT_PROCESSING_CALLBACK_TOKEN
movo_prepare_internal_service_auth "$fixture_root"
test "$MOVO_DOC_PROCESSING_CALLBACK_TOKEN" = "persisted-callback-token"
test "$ASKAI_ADMIN_DOCUMENT_PROCESSING_CALLBACK_TOKEN" = "persisted-callback-token"

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

ASKAI_ADMIN_JWT_SECRET="canonical-jwt-secret"
MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET="stale-jwt-secret"
movo_prepare_internal_service_auth
test "$ASKAI_ADMIN_JWT_SECRET" = "canonical-jwt-secret"
test "$MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET" = "canonical-jwt-secret"

echo "internal service auth checks passed"
