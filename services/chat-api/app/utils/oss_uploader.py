from __future__ import annotations

import datetime
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional
from urllib.parse import quote, unquote, urlparse

import oss2

from app.core.config import get_settings
from app.services.local_file_signing import sign_local_file_url


class _LocalBucketProxy:
    def __init__(self, owner: "ObjectStorageClient") -> None:
        self._owner = owner

    def put_object(self, object_path: str, content, headers: Optional[Dict[str, str]] = None) -> None:
        content_type = ""
        if isinstance(headers, dict):
            content_type = str(headers.get("Content-Type") or "").strip()
        self._owner.write_bytes(object_path, self._owner._coerce_bytes(content), content_type=content_type or None)


class ObjectStorageClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self.storage_backend = str(settings.STORAGE_BACKEND or "oss").strip().lower() or "oss"
        self.local_storage_path = Path(str(settings.LOCAL_STORAGE_PATH or "storage")).expanduser()
        self.file_public_base_url = str(settings.FILE_PUBLIC_BASE_URL or "").strip().rstrip("/")
        self.file_public_path_prefix = "/" + str(settings.FILE_PUBLIC_PATH_PREFIX or "/askai-api/api/files").strip().strip("/")
        self.backend_internal_base_url = str(settings.BACKEND_INTERNAL_BASE_URL or "http://127.0.0.1:8000").strip().rstrip("/")
        self.bucket_name = settings.OSS_BUCKET_NAME
        self.endpoint = settings.OSS_ENDPOINT
        self.region = settings.OSS_REGION
        self.auth = None
        self.bucket = None

        if self.storage_backend == "local":
            self.local_storage_path.mkdir(parents=True, exist_ok=True)
            self.bucket = _LocalBucketProxy(self)
            return

        access_key_id = settings.OSS_ACCESS_KEY_ID
        access_key_secret = settings.OSS_ACCESS_KEY_SECRET
        if not access_key_id or not access_key_secret:
            raise RuntimeError("OSS credentials are missing. Set OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET in .env.")

        self.auth = oss2.Auth(access_key_id, access_key_secret)
        self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name, region=self.region)

    def generate_object_path(self, user_id: str, file_name: str, now: Optional[datetime.datetime] = None) -> str:
        timestamp = (now or datetime.datetime.utcnow()).strftime("%Y/%m/%d/%H/%M/%S")
        safe_user_id = str(user_id).strip() or "anonymous"
        safe_user_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in safe_user_id)
        safe_name = os.path.basename(str(file_name or "").strip() or "file.bin")
        safe_name = safe_name.replace("\\", "_").replace("/", "_")
        return f"{safe_user_id}/{timestamp}/{safe_name}"

    def _coerce_bytes(self, content) -> bytes:
        if isinstance(content, bytes):
            return content
        if hasattr(content, "read"):
            stream = content
            assert isinstance(stream, BinaryIO)
            data = stream.read()
            return data if isinstance(data, bytes) else bytes(data or b"")
        return bytes(content or b"")

    def _local_file_path(self, object_path: str) -> Path:
        token = str(object_path or "").strip().lstrip("/")
        if not token:
            raise ValueError("object_path is required")
        candidate = (self.local_storage_path / token).resolve()
        root = self.local_storage_path.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("object_path escapes storage root") from exc
        return candidate

    def local_file_path(self, object_path: str) -> Path:
        if self.storage_backend != "local":
            raise RuntimeError("local_file_path is only available when STORAGE_BACKEND=local")
        return self._local_file_path(object_path)

    def _build_public_url(self, object_path: str, *, absolute: bool) -> str:
        quoted = quote(str(object_path or "").strip().lstrip("/"), safe="/")
        path_prefix = "/api/files" if absolute else self.file_public_path_prefix
        path = f"{path_prefix}/{quoted}"
        if absolute:
            return f"{self.backend_internal_base_url}/api/files/{quoted}"
        if self.file_public_base_url:
            return f"{self.file_public_base_url}{path}"
        return path

    def upload_file(self, local_file_path: str, user_id: str) -> str:
        url, _object_path = self.upload_file_with_path(local_file_path, user_id)
        return url

    def upload_file_with_path(self, local_file_path: str, user_id: str) -> tuple[str, str]:
        if not os.path.exists(local_file_path):
            raise FileNotFoundError(f"File not found: {local_file_path}")
        file_name = os.path.basename(local_file_path)
        with open(local_file_path, "rb") as fileobj:
            content = fileobj.read()
        content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        return self.upload_bytes_with_path(content, user_id, file_name, content_type=content_type)

    def upload_bytes(self, content: bytes, user_id: str, file_name: str, content_type: Optional[str] = None) -> str:
        url, _object_path = self.upload_bytes_with_path(content, user_id, file_name, content_type=content_type)
        return url

    def upload_bytes_with_path(
        self,
        content: bytes,
        user_id: str,
        file_name: str,
        content_type: Optional[str] = None,
    ) -> tuple[str, str]:
        object_path = self.generate_object_path(user_id, file_name)
        data = self._coerce_bytes(content)
        if self.storage_backend == "local":
            self.write_bytes(object_path, data, content_type=content_type)
            return self.sign_url(object_path), object_path

        headers = {"Content-Type": content_type} if content_type else None
        assert self.bucket is not None
        self.bucket.put_object(object_path, data, headers=headers)
        url = f"https://{self.bucket_name}.{self.endpoint.split('//')[1]}/{object_path}"
        return url, object_path

    def write_bytes(self, object_path: str, content: bytes, *, content_type: Optional[str] = None) -> None:
        data = self._coerce_bytes(content)
        if self.storage_backend == "local":
            file_path = self._local_file_path(object_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(data)
            if content_type:
                meta_path = file_path.with_suffix(file_path.suffix + ".meta")
                meta_path.write_text(f"content_type={content_type}\n", encoding="utf-8")
            return

        headers = {"Content-Type": content_type} if content_type else None
        assert self.bucket is not None
        self.bucket.put_object(object_path, data, headers=headers)

    def read_bytes(self, object_path: str) -> bytes:
        path = str(object_path or "").strip()
        if not path:
            return b""
        if self.storage_backend == "local":
            file_path = self._local_file_path(path)
            return file_path.read_bytes()

        signed = self.sign_url(path)
        import httpx

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(signed)
            resp.raise_for_status()
            return resp.content or b""

    def guess_content_type(self, object_path: str) -> str:
        path = str(object_path or "").strip()
        if self.storage_backend == "local":
            file_path = self._local_file_path(path)
            meta_path = file_path.with_suffix(file_path.suffix + ".meta")
            if meta_path.exists():
                try:
                    for line in meta_path.read_text(encoding="utf-8").splitlines():
                        if line.startswith("content_type="):
                            return line.split("=", 1)[1].strip()
                except Exception:
                    pass
        guessed, _encoding = mimetypes.guess_type(path)
        return guessed or "application/octet-stream"

    def sign_url(self, object_path: str, expires: Optional[int] = None) -> str:
        if self.storage_backend == "local":
            ttl = expires if expires is not None else get_settings().OSS_SIGN_EXPIRE_SECONDS
            return sign_local_file_url(
                self._build_public_url(object_path, absolute=False),
                object_path,
                secret=str(self._settings.END_USER_AUTH_SECRET or ""),
                ttl_seconds=ttl,
            )
        ttl = expires if expires is not None else get_settings().OSS_SIGN_EXPIRE_SECONDS
        assert self.bucket is not None
        return self.bucket.sign_url("GET", object_path, ttl)

    def internal_url(self, object_path: str) -> str:
        if self.storage_backend == "local":
            return sign_local_file_url(
                self._build_public_url(object_path, absolute=True),
                object_path,
                secret=str(self._settings.END_USER_AUTH_SECRET or ""),
                ttl_seconds=self._settings.OSS_SIGN_EXPIRE_SECONDS,
            )
        return self.sign_url(object_path)

    def object_path_from_url(self, url: str) -> str:
        value = str(url or "").strip()
        if not value:
            return ""
        if self.storage_backend == "local":
            try:
                parsed = urlparse(value)
            except Exception:
                return ""
            path = str(parsed.path or "").strip()
            prefixes = {
                self.file_public_path_prefix.rstrip("/"),
                "/api/files",
            }
            for prefix in prefixes:
                if path.startswith(prefix + "/"):
                    return unquote(path[len(prefix) + 1 :]).strip()
            return ""

        try:
            parsed = urlparse(value)
        except Exception:
            return ""
        endpoint_host = self.endpoint.split("//", 1)[-1].strip("/")
        asset_host = f"{self.bucket_name}.{endpoint_host}"
        host = str(parsed.netloc or "").lower()
        path = unquote(str(parsed.path or "").lstrip("/")).strip()
        if host == asset_host.lower() or host.startswith(f"{self.bucket_name.lower()}."):
            return path
        if host == endpoint_host.lower() and path.startswith(f"{self.bucket_name}/"):
            return path.split("/", 1)[1].strip()
        return ""

    @staticmethod
    def parse_oss_url(url: str) -> Dict[str, str]:
        value = str(url or "").strip()
        if not value:
            return {}
        try:
            parsed = urlparse(value)
        except Exception:
            return {}
        host = str(parsed.netloc or "").strip().lower()
        path = unquote(str(parsed.path or "").lstrip("/")).strip()
        if not host or not path:
            return {}

        virtual_match = re.match(r"^(?P<bucket>[a-z0-9][a-z0-9-]{1,62})\.(?P<endpoint>oss-[a-z0-9-]+\.aliyuncs\.com)$", host)
        if virtual_match:
            endpoint_host = virtual_match.group("endpoint")
            region_match = re.match(r"^oss-(?P<region>[a-z0-9-]+)\.aliyuncs\.com$", endpoint_host)
            return {
                "bucket": virtual_match.group("bucket"),
                "endpoint": f"https://{endpoint_host}",
                "endpoint_host": endpoint_host,
                "region": region_match.group("region") if region_match else "",
                "object_path": path,
            }

        path_match = re.match(r"^(?P<endpoint>oss-[a-z0-9-]+\.aliyuncs\.com)$", host)
        if path_match and "/" in path:
            bucket, object_path = path.split("/", 1)
            if bucket and object_path:
                endpoint_host = path_match.group("endpoint")
                region_match = re.match(r"^oss-(?P<region>[a-z0-9-]+)\.aliyuncs\.com$", endpoint_host)
                return {
                    "bucket": bucket,
                    "endpoint": f"https://{endpoint_host}",
                    "endpoint_host": endpoint_host,
                    "region": region_match.group("region") if region_match else "",
                    "object_path": object_path,
                }
        return {}

    def sign_url_from_url(self, url: str, expires: Optional[int] = None) -> str:
        if self.storage_backend == "local":
            object_path = self.object_path_from_url(url)
            return self.sign_url(object_path, expires=expires) if object_path else ""

        parsed = self.parse_oss_url(url)
        if not parsed:
            return ""
        bucket_name = str(parsed.get("bucket") or "").strip()
        endpoint = str(parsed.get("endpoint") or "").strip()
        object_path = str(parsed.get("object_path") or "").strip()
        if not bucket_name or not endpoint or not object_path:
            return ""
        ttl = expires if expires is not None else get_settings().OSS_SIGN_EXPIRE_SECONDS
        if bucket_name == self.bucket_name and endpoint.rstrip("/") == self.endpoint.rstrip("/"):
            return self.sign_url(object_path, ttl)
        bucket = oss2.Bucket(
            self.auth,
            endpoint,
            bucket_name,
            region=str(parsed.get("region") or "") or None,
        )
        return bucket.sign_url("GET", object_path, ttl)

    def refresh_markdown_urls(self, markdown: str) -> str:
        if not markdown:
            return markdown
        if self.storage_backend == "local":
            prefixes = {
                self.file_public_path_prefix.rstrip("/"),
                "/api/files",
            }
            refreshed = markdown
            for prefix in prefixes:
                pattern = re.compile(rf"{re.escape(prefix)}/[^\s)>\]\"']+")
                refreshed = pattern.sub(
                    lambda match: self._refresh_url_string(match.group(0)),
                    refreshed,
                )
            return refreshed

        endpoint_host = self.endpoint.split("//", 1)[-1].strip("/")
        asset_host = f"{self.bucket_name}.{endpoint_host}"
        url_pattern = re.compile(rf"https://{re.escape(asset_host)}/[^\s)>\]\"']+")
        cache: dict[str, str] = {}

        def _replace(match: re.Match[str]) -> str:
            original_url = match.group(0)
            cached = cache.get(original_url)
            if cached:
                return cached
            try:
                parsed = urlparse(original_url)
                object_path = unquote(parsed.path.lstrip("/"))
                if not object_path:
                    return original_url
                renewed = self.sign_url(object_path)
                cache[original_url] = renewed
                return renewed
            except Exception:
                return original_url

        return url_pattern.sub(_replace, markdown)

    def refresh_json_urls(self, payload: Any) -> tuple[Any, int]:
        if not isinstance(payload, (dict, list)):
            return payload, 0

        refreshed_count = 0

        def _refresh(value: Any) -> Any:
            nonlocal refreshed_count
            if isinstance(value, dict):
                return {key: _refresh(item) for key, item in value.items()}
            if isinstance(value, list):
                return [_refresh(item) for item in value]
            if not isinstance(value, str):
                return value
            renewed = self._refresh_url_string(value)
            if renewed != value:
                refreshed_count += 1
            return renewed

        return _refresh(payload), refreshed_count

    def _refresh_url_string(self, value: str) -> str:
        source = str(value or "").strip()
        if not source.startswith(("http://", "https://", "/")):
            return value
        object_path = self.object_path_from_url(source)
        if object_path:
            try:
                return self.sign_url(object_path)
            except Exception:
                return value
        try:
            renewed = self.sign_url_from_url(source)
        except Exception:
            renewed = ""
        return renewed or value


# Backward-compatible alias for existing business code. New code should import
# ObjectStorageClient to avoid implying that the configured backend is always OSS.
AliyunOSSUploader = ObjectStorageClient
