from __future__ import annotations

import ssl
import urllib.error

import certifi

from app.core.config import settings


def build_model_test_ssl_context() -> ssl.SSLContext:
    if settings.model_test_insecure_skip_verify:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    ca_bundle = settings.model_test_ca_bundle.strip()
    if ca_bundle:
        return ssl.create_default_context(cafile=ca_bundle)
    return ssl.create_default_context(cafile=certifi.where())


def format_model_test_url_error(exc: urllib.error.URLError, *, service_name: str = "模型接口") -> str:
    reason = str(exc.reason)
    if "CERTIFICATE_VERIFY_FAILED" in reason:
        return (
            f"{service_name} TLS 证书校验失败。"
            "服务将使用 certifi CA 证书库；如上游使用企业私有 CA，请配置 "
            "ASKAI_ADMIN_MODEL_TEST_CA_BUNDLE=<CA证书路径>。"
            "仅开发环境可临时设置 ASKAI_ADMIN_MODEL_TEST_INSECURE_SKIP_VERIFY=true。"
            f" 原始错误: {reason}"
        )
    return f"无法连接{service_name}: {reason}"


__all__ = ["build_model_test_ssl_context", "format_model_test_url_error"]
