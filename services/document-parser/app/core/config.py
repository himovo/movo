from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_PREFIX = "MOVO_DOC_PROCESSING_"
LEGACY_ENV_PREFIX = "ASKAI_DOC_PROCESSING_"


class Settings(BaseSettings):
    app_env: str = "development"
    service_token: str = ""
    callback_token: str = ""
    local_storage_dir: str = "../admin-api/data/knowledge-documents"
    artifacts_prefix: str = "artifacts"
    oss_endpoint: str = "https://oss-cn-beijing.aliyuncs.com"
    oss_bucket: str = "askagentic"
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    libreoffice_bin: str = ""
    conversion_timeout_seconds: int = 180
    max_concurrent_jobs: int = 2
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_queue: str = "document_processing"
    mongodb_uri: str = ""
    mongodb_db: str = ""
    jobs_collection: str = "document_jobs"
    azure_embedding_endpoint: str = ""
    azure_embedding_deployment_name: str = "text_embedding"
    azure_embedding_api_version: str = "2025-04-01-preview"
    azure_embedding_api_key: str = ""
    weaviate_endpoint: str = "http://127.0.0.1:8080"
    weaviate_api_key: str = ""
    weaviate_collection_name: str = "AskAIKnowledgeChunks"
    weaviate_distance_metric: str = "cosine"
    dashscope_api_key: str = ""
    admin_jwt_secret: str = ""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
        extra="ignore",
    )

    @property
    def resolved_local_storage_dir(self) -> str:
        return str(Path(self.local_storage_dir).expanduser().resolve())

    @property
    def effective_mongodb_uri(self) -> str:
        return self.mongodb_uri or os.getenv("MONGODB_URI", "") or _read_env_file_value("MONGODB_URI")

    @property
    def effective_mongodb_db(self) -> str:
        return self.mongodb_db or os.getenv("MONGODB_DB", "") or _read_env_file_value("MONGODB_DB") or "gragentic"


def _read_env_file_value(key: str) -> str:
    candidate_paths = [
        Path(".env"),
        Path("../admin-api/.env"),
        Path("../../services/admin-api/.env"),
        Path("../chat-api/.env"),
        Path("../../services/chat-api/.env"),
        Path("../admin/api/.env"),
        Path("../../admin/api/.env"),
        Path("../backend/.env"),
        Path("../../backend/.env"),
        Path("backend/.env"),
    ]
    for candidate_path in candidate_paths:
        if not candidate_path.exists():
            continue
        try:
            for raw_line in candidate_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                current_key, current_value = line.split("=", 1)
                if current_key.strip() == key:
                    return current_value.strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def _apply_legacy_env_prefix(current_settings: Settings) -> None:
    for field_name, field_info in Settings.model_fields.items():
        env_name = f"{field_name}".upper()
        new_key = f"{ENV_PREFIX}{env_name}"
        legacy_key = f"{LEGACY_ENV_PREFIX}{env_name}"
        if os.getenv(new_key, "") or _read_env_file_value(new_key):
            continue
        raw_value = os.getenv(legacy_key, "") or _read_env_file_value(legacy_key)
        if raw_value == "":
            continue
        annotation = field_info.annotation
        if annotation is int:
            try:
                setattr(current_settings, field_name, int(raw_value))
            except ValueError:
                continue
        else:
            setattr(current_settings, field_name, raw_value)


settings = Settings()
_apply_legacy_env_prefix(settings)
if not settings.mongodb_uri:
    settings.mongodb_uri = settings.effective_mongodb_uri
if not settings.mongodb_db:
    settings.mongodb_db = settings.effective_mongodb_db
if not settings.oss_access_key_id:
    settings.oss_access_key_id = os.getenv("OSS_ACCESS_KEY_ID", "") or _read_env_file_value("OSS_ACCESS_KEY_ID")
if not settings.oss_access_key_secret:
    settings.oss_access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET", "") or _read_env_file_value("OSS_ACCESS_KEY_SECRET")
if not settings.oss_endpoint:
    settings.oss_endpoint = os.getenv("OSS_ENDPOINT", "") or _read_env_file_value("OSS_ENDPOINT") or "https://oss-cn-beijing.aliyuncs.com"
if not settings.oss_bucket:
    settings.oss_bucket = (
        os.getenv("OSS_BUCKET_NAME", "")
        or os.getenv("OSS_BUCKET", "")
        or _read_env_file_value("OSS_BUCKET_NAME")
        or _read_env_file_value("OSS_BUCKET")
        or "askagentic"
    )
if not settings.azure_embedding_api_key:
    settings.azure_embedding_api_key = (
        os.getenv("AZURE_EMBEDDING_API_KEY", "")
        or os.getenv("AZURE_OPENAI_API_KEY", "")
        or os.getenv("OPENAI_API_KEY", "")
        or _read_env_file_value("AZURE_EMBEDDING_API_KEY")
        or _read_env_file_value("AZURE_OPENAI_API_KEY")
        or _read_env_file_value("OPENAI_API_KEY")
    )
if not settings.dashscope_api_key:
    settings.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "") or _read_env_file_value("DASHSCOPE_API_KEY")
if not settings.admin_jwt_secret:
    settings.admin_jwt_secret = os.getenv("JWT_SECRET", "") or _read_env_file_value("JWT_SECRET")
