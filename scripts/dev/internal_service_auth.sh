#!/usr/bin/env bash

_movo_read_env_value() {
    local key="$1"
    local file="$2"
    local line value

    [ -f "$file" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            "$key="*)
                value="${line#*=}"
                value="${value%$'\r'}"
                if [[ "$value" == \"*\" && "$value" == *\" ]]; then
                    value="${value:1:${#value}-2}"
                elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
                    value="${value:1:${#value}-2}"
                fi
                printf '%s' "$value"
                return 0
                ;;
        esac
    done < "$file"
}

# Prepare credentials shared by source-development services. The optional
# repository root lets this function reuse persisted local secrets without
# sourcing .env files as executable shell code.
movo_prepare_internal_service_auth() {
    local root_dir="${1:-}"
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

    # admin-api -> document-parser uses a separate shared credential. Source
    # development must export both services' variable names; otherwise the
    # parser starts with an empty token and rejects every learning job.
    local document_token="${MOVO_DOC_PROCESSING_SERVICE_TOKEN:-${ASKAI_ADMIN_DOCUMENT_PROCESSING_SERVICE_TOKEN:-}}"
    if [ -z "$document_token" ]; then
        if command -v openssl >/dev/null 2>&1; then
            document_token="$(openssl rand -hex 32)"
        else
            document_token="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
        fi
    fi
    export MOVO_DOC_PROCESSING_SERVICE_TOKEN="$document_token"
    export ASKAI_ADMIN_DOCUMENT_PROCESSING_SERVICE_TOKEN="$document_token"
    export DOCUMENT_PROCESSING_SERVICE_TOKEN="$document_token"

    # Preview callbacks from document-parser must use the same token that
    # chat-api and admin-api validate, including in source-development mode.
    local callback_token="${MOVO_DOC_PROCESSING_CALLBACK_TOKEN:-${ASKAI_ADMIN_DOCUMENT_PROCESSING_CALLBACK_TOKEN:-}}"
    if [ -z "$callback_token" ] && [ -n "$root_dir" ]; then
        callback_token="$(_movo_read_env_value ASKAI_ADMIN_DOCUMENT_PROCESSING_CALLBACK_TOKEN "$root_dir/services/admin-api/.env")"
    fi
    if [ -z "$callback_token" ] && [ -n "$root_dir" ]; then
        callback_token="$(_movo_read_env_value MOVO_DOC_PROCESSING_CALLBACK_TOKEN "$root_dir/services/document-parser/.env")"
    fi
    if [ -z "$callback_token" ]; then
        if command -v openssl >/dev/null 2>&1; then
            callback_token="$(openssl rand -hex 32)"
        else
            callback_token="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
        fi
    fi
    export MOVO_DOC_PROCESSING_CALLBACK_TOKEN="$callback_token"
    export ASKAI_ADMIN_DOCUMENT_PROCESSING_CALLBACK_TOKEN="$callback_token"

    # Model Center secrets are encrypted by admin-api with its JWT secret and
    # decrypted by both the document API and Celery worker. They must receive
    # the exact same stable value or every embedding/rerank key is unreadable.
    local admin_jwt_secret="${ASKAI_ADMIN_JWT_SECRET:-${MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET:-}}"
    if [ -z "$admin_jwt_secret" ] && [ -n "$root_dir" ]; then
        admin_jwt_secret="$(_movo_read_env_value ASKAI_ADMIN_JWT_SECRET "$root_dir/services/admin-api/.env")"
    fi
    if [ -z "$admin_jwt_secret" ] && [ -n "$root_dir" ]; then
        admin_jwt_secret="$(_movo_read_env_value MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET "$root_dir/services/document-parser/.env")"
    fi
    if [ -z "$admin_jwt_secret" ] && [ -n "$root_dir" ]; then
        admin_jwt_secret="$(_movo_read_env_value JWT_SECRET "$root_dir/services/chat-api/.env")"
    fi
    local generated_secret_file=""
    if [ -z "$admin_jwt_secret" ] && [ -n "$root_dir" ]; then
        generated_secret_file="$root_dir/.movo-dev/admin_jwt_secret"
        if [ -s "$generated_secret_file" ]; then
            IFS= read -r admin_jwt_secret < "$generated_secret_file"
        else
            mkdir -p "$(dirname "$generated_secret_file")"
            chmod 700 "$(dirname "$generated_secret_file")"
            if command -v openssl >/dev/null 2>&1; then
                admin_jwt_secret="$(openssl rand -hex 32)"
            elif command -v python3 >/dev/null 2>&1; then
                admin_jwt_secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
            fi
            if [ -n "$admin_jwt_secret" ]; then
                (umask 077 && printf '%s\n' "$admin_jwt_secret" > "$generated_secret_file")
            fi
        fi
    fi
    if [ -z "$admin_jwt_secret" ]; then
        echo "A stable admin JWT secret is required for Model Center credentials." >&2
        echo "Set ASKAI_ADMIN_JWT_SECRET in services/admin-api/.env and restart ./dev.sh." >&2
        return 1
    fi
    export ASKAI_ADMIN_JWT_SECRET="$admin_jwt_secret"
    export MOVO_DOC_PROCESSING_ADMIN_JWT_SECRET="$admin_jwt_secret"
}
