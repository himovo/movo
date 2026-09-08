#!/usr/bin/env bash

# Prepare the shared credential used only for trusted admin-api -> chat-api
# requests. Both names are exported for compatibility, but ADMIN_BACKEND_SERVICE_TOKEN
# is the canonical source.
movo_prepare_internal_service_auth() {
    local token="${ADMIN_BACKEND_SERVICE_TOKEN:-${ASKAI_ADMIN_BACKEND_SERVICE_TOKEN:-}}"

    if [ -z "$token" ]; then
        if command -v openssl >/dev/null 2>&1; then
            token="$(openssl rand -hex 32)"
        elif command -v python3 >/dev/null 2>&1; then
            token="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
        else
            echo "Unable to generate the internal service token: openssl or python3 is required." >&2
            return 1
        fi
    fi

    export ADMIN_BACKEND_SERVICE_TOKEN="$token"
    export ASKAI_ADMIN_BACKEND_SERVICE_TOKEN="$token"
}
