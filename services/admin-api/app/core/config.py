import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    cors_origins: list[str] = ["http://localhost:3100"]
    mongodb_uri: str = ""
    mongodb_db: str = ""
    jwt_secret: str = ""
    access_token_ttl_seconds: int = 60 * 60 * 12
    bootstrap_admin_enabled: bool = False
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""
    bootstrap_admin_display_name: str = "系统管理员"
    bootstrap_admin_role_name: str = "平台超级管理员"
    bootstrap_admin_org_name: str = "MOVO 平台"
    bootstrap_main_id: str = "default"
    user_portal_base_url: str = "http://localhost:3100"
    invite_token_ttl_hours: int = 72
    model_test_ca_bundle: str = ""
    model_test_insecure_skip_verify: bool = False
    backend_base_url: str = "http://127.0.0.1:8000"
    backend_service_token: str = ""
    public_base_url: str = ""
    redis_url: str = "redis://127.0.0.1:6379/0"
    weaviate_endpoint: str = "http://127.0.0.1:8080"
    knowledge_storage_type: str = "local"
    knowledge_local_storage_dir: str = "data/knowledge-documents"
    knowledge_max_upload_mb: int = 200
    knowledge_allowed_extensions: str = "pdf,doc,docx,ppt,pptx,xls,xlsx,txt,md,png,jpg,jpeg,webp"
    knowledge_oss_endpoint: str = "https://oss-cn-beijing.aliyuncs.com"
    knowledge_oss_bucket: str = "askagentic"
    knowledge_oss_access_key_id: str = ""
    knowledge_oss_access_key_secret: str = ""
    knowledge_oss_prefix: str = "knowledge-documents"
    document_processing_base_url: str = "http://127.0.0.1:8200"
    document_processing_service_token: str = ""
    document_processing_callback_token: str = ""
    admin_api_public_base_url: str = "http://127.0.0.1:8101"
    admin_static_dir: str = "data/admin-static"
    avatar_max_upload_mb: int = 2
    knowledge_min_chunk_size: int = 800
    knowledge_chunk_size: int = 1500
    knowledge_chunk_overlap: int = 120

    model_config = SettingsConfigDict(
        env_prefix="ASKAI_ADMIN_",
        env_file=".env",
        extra="ignore",
    )

    @property
    def effective_mongodb_uri(self) -> str:
        return self.mongodb_uri or os.getenv("MONGODB_URI", "") or _read_env_file_value("MONGODB_URI")

    @property
    def effective_mongodb_db(self) -> str:
        return self.mongodb_db or os.getenv("MONGODB_DB", "") or _read_env_file_value("MONGODB_DB") or "gragentic"

def _read_env_file_value(key: str) -> str:
    candidate_paths = [
        Path(".env"),
        Path("../chat-api/.env"),
        Path("../../services/chat-api/.env"),
        Path("../../backend/.env"),
        Path("../backend/.env"),
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


settings = Settings()
if not settings.mongodb_uri:
    settings.mongodb_uri = settings.effective_mongodb_uri
if not settings.mongodb_db:
    settings.mongodb_db = settings.effective_mongodb_db
if not settings.knowledge_oss_access_key_id:
    settings.knowledge_oss_access_key_id = os.getenv("OSS_ACCESS_KEY_ID", "") or _read_env_file_value("OSS_ACCESS_KEY_ID")
if not settings.knowledge_oss_access_key_secret:
    settings.knowledge_oss_access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET", "") or _read_env_file_value("OSS_ACCESS_KEY_SECRET")
