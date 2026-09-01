from pydantic import field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "MOVO"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8080"
    
    # OpenAI
    # Model credentials are configured after the self-hosted control plane is
    # available, so an empty key must not prevent the API container from booting.
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    OPENAI_MODEL_GENERAL: str = "gpt-5.2"
    OPENAI_MODEL_CHAT: str = "gpt-5.2-chat"
    OPENAI_MODEL_CODING: str = "gpt-5.3-codex"

    # Azure OpenAI
    USE_AZURE: bool = False
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2023-05-15"
    AZURE_DEPLOYMENT_NAME: str = ""
    AZURE_DEPLOYMENT_CHAT: str = ""
    AZURE_DEPLOYMENT_GENERAL: str = ""
    AZURE_DEPLOYMENT_CODING: str = ""

    # Azure GPT Image

    # Qwen (DashScope OpenAI-compatible)
    USE_QWEN: bool = False
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    # Multimodal Vision (DashScope OpenAI-compatible)
    USE_MULTIMODAL: bool = True
    DASHSCOPE_API_KEY: str = ""
    VISION_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    VISION_MODEL: str = "qwen3-vl-plus"
    VISION_ENABLE_THINKING: bool = True
    VISION_THINKING_BUDGET: int = 81920

    # Deep Search
    SERPAPI_API_KEY: str = ""  # Set via env; leave empty to disable
    SERPAPI_ENABLED: bool = False  # Disable SerpAPI when quota is exhausted
    SERPER_API_KEY: str = ""  # Set via env for google.serper.dev
    TAVILY_API_KEY: str = ""  # Set via env for Tavily search
    BAIDU_QIANFAN_API_KEY: str = ""  # Set via env for Baidu Qianfan ai_search/web_search
    BAIDU_QIANFAN_SEARCH_URL: str = "https://qianfan.baidubce.com/v2/ai_search/web_search"
    ARK_API_KEY: str = ""  # Set via env for Volcengine Ark Bot
    ARK_BOT_MODEL: str = ""  # e.g. bot-20260218195230-n4jrq
    ARK_BOT_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3/bots"
    CRAWLER_API_URL: str = "http://localhost:8000/crawler"
    DOC_PARSER_API_URL: str = ""
    TOKEN_USAGE_PUSH_ENABLED: bool = False
    TOKEN_USAGE_PUSH_URL: str = ""
    TOKEN_USAGE_PUSH_TIMEOUT_SECONDS: float = 2.0
    TOKEN_USAGE_QUEUE_SIZE: int = 512

    # Internal knowledge base retrieval. When configured, kb_search calls this
    # service directly and does not fall back to local chat/session retrieval.
    KNOWLEDGE_CANDIDATES_API_URL: str = ""
    KNOWLEDGE_CANDIDATES_BASE_URL: str = ""
    KNOWLEDGE_CANDIDATES_TIMEOUT_SECONDS: float = 20.0
    KNOWLEDGE_CANDIDATES_MIN_RERANK_SCORE: float = 10.0
    DOCUMENT_PROCESSING_BASE_URL: str = "http://127.0.0.1:8200"
    DOCUMENT_PROCESSING_SERVICE_TOKEN: str = ""
    DOCUMENT_PROCESSING_TIMEOUT_SECONDS: float = 30.0
    DOCUMENT_PROCESSING_SYNC_PARSE_TIMEOUT_SECONDS: float = 180.0
    KNOWLEDGE_STORAGE_TYPE: str = "local"
    KNOWLEDGE_LOCAL_STORAGE_DIR: str = "../admin-api/data/knowledge-documents"
    KNOWLEDGE_OSS_BUCKET: str = ""
    KNOWLEDGE_OSS_ENDPOINT: str = ""
    
    # Financial Data
    TUSHARE_TOKEN: str | None = None
    
    # Tianyancha
    TIANYANCHA_TOKEN: str = ""

    # MongoDB
    MONGODB_URI: str = ""
    MONGODB_DB: str = "gragentic"
    END_USER_AUTH_TOKEN_TTL_SECONDS: int = 60 * 60 * 24 * 7
    END_USER_AUTH_SECRET: str = ""
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FILE_ENABLED: bool = False
    LOG_FILE_PATH: str = "backend.log"
    LOG_FILE_FORMAT: str = "json"
    LOG_CONSOLE_PRETTY: bool = True
    LOG_CAPTURE_PRINTS: bool = True
    LOG_DEBUG_PAYLOADS: bool = False
    LOG_REQUEST_HEARTBEAT_SECONDS: float = 15.0
    LOG_SLOW_SPAN_MS: int = 10000
    LLM_SLOW_MS: int = 30000
    TOOL_SLOW_MS: int = 20000
    DB_SLOW_MS: int = 3000
    PRESENTATION_PAGE_SLOW_MS: int = 20000
    DEBUG_ARTIFACTS_ENABLED: bool = False
    DEBUG_ARTIFACT_RETENTION_DAYS: int = 7
    REQUEST_DEBUG_SNAPSHOT_ENABLED: bool = False
    ENABLE_BROWSER_PLANNING: bool = True
    ENABLE_CODING_PLANNING: bool = True
    PLAN_ONLY_MODE: bool = False
    PIPELINE_MODE: str = "task_network"
    # Deprecated — retained so existing .env files continue to load. The
    # presentation pipeline now trusts the LLM's first-shot geometry and has no
    # repair / normalize / fast-mode / raw-render switches to toggle.
    PRESENTATION_PIPELINE_VERSION: str = ""
    PRESENTATION_IMAGE_NATIVE_PAGE_CONCURRENCY: int = 2
    PRESENTATION_RAW_RENDER: str = ""
    PRESENTATION_V5_RAW_RENDER: str = ""
    PRESENTATION_V5_FAST_MODE: str = ""
    PRESENTATION_FAST_MODE: str = ""
    ASKAI_ADMIN_JWT_SECRET: str = ""
    ADMIN_BACKEND_SERVICE_TOKEN: str = ""
    DSH_MODEL_GATEWAY_SIGNING_SECRET: str = ""
    DSH_TOOL_GATEWAY_URL: str = "http://127.0.0.1:8000/internal/dsh/tools"
    DSH_RUNTIME_HOST_URL: str = "http://127.0.0.1:8101"
    DSH_RUNTIME_HOST_TOKEN: str = ""
    DSH_MODEL_GATEWAY_URL: str = "http://127.0.0.1:8000/internal/dsh/model/generate"
    DSH_RUNTIME_HTTP_TIMEOUT_SECONDS: float = 5.0

    # Optional demo APIs are excluded from production by default.
    ENABLE_DEMO_ENDPOINTS: bool = False
    # Upload limits. Defaults are intentionally generous to preserve existing
    # workflows while preventing accidental unbounded in-memory reads.
    MAX_UPLOAD_IMAGE_BYTES: int = 50 * 1024 * 1024
    MAX_UPLOAD_DOCUMENT_BYTES: int = 200 * 1024 * 1024
    MAX_UPLOAD_SKILL_SOURCE_BYTES: int = 200 * 1024 * 1024
    MAX_UPLOAD_TEMPLATE_BYTES: int = 200 * 1024 * 1024

    # Object storage. STORAGE_BACKEND=oss preserves the existing enterprise
    # Aliyun OSS behavior; STORAGE_BACKEND=local stores artifacts on disk and
    # serves them through /api/files.
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "storage"
    FILE_PUBLIC_BASE_URL: str = ""
    FILE_PUBLIC_PATH_PREFIX: str = "/askai-api/api/files"
    BACKEND_INTERNAL_BASE_URL: str = "http://127.0.0.1:8000"
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET_NAME: str = "movo-artifacts"
    OSS_ENDPOINT: str = "https://oss-cn-beijing.aliyuncs.com"
    OSS_REGION: str = "cn-beijing"
    OSS_SIGN_EXPIRE_SECONDS: int = 3600

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _normalize_debug(cls, value):
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"release", "prod", "production", "false", "0", "off", "no"}:
                return False
            if lowered in {"debug", "true", "1", "on", "yes"}:
                return True
        return value

    def allowed_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in str(self.ALLOWED_ORIGINS or "").split(",")
            if origin.strip()
        ]

    def is_planning_intent_enabled(self, intent: str) -> bool:
        token = str(intent or "").strip().lower()
        if token == "task":
            return True
        if token == "browser_automation":
            return bool(self.ENABLE_BROWSER_PLANNING)
        if token == "coding":
            return bool(self.ENABLE_CODING_PLANNING)
        return True

    def allowed_planning_intents(self) -> list[str]:
        intents = ["chat", "task"]
        return [intent for intent in intents if self.is_planning_intent_enabled(intent)]

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

@lru_cache()
def get_settings():
    return Settings()
