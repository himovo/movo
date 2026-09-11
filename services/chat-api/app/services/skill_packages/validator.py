from __future__ import annotations

import hashlib
import io
import json
import posixpath
import re
import stat
import zipfile
from dataclasses import dataclass
from typing import Any, Literal

import yaml


MAX_ARCHIVE_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 256
MAX_COMPRESSION_RATIO = 200
SKILL_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,125}[a-z0-9])?$")
SKILL_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
TOOL_REFERENCE = re.compile(r"^\s*([a-z][a-z0-9_]{1,63})\s*\(", re.MULTILINE)
FENCED_CODE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
IGNORED_PREFIXES = ("__MACOSX/",)


class SkillPackageError(ValueError):
    def __init__(self, code: str, message: str, *, file: str = "", field: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.file = file
        self.field = field

    def detail(self) -> dict[str, str]:
        return {key: value for key, value in {
            "code": self.code, "message": self.message, "file": self.file, "field": self.field,
        }.items() if value}


@dataclass(frozen=True)
class ValidatedSkillPackage:
    name: str
    display_name: str
    description: str
    when_to_use: str
    version: str
    markdown: str
    metadata: dict[str, Any]
    market_metadata: dict[str, Any]
    root_prefix: str
    archive_digest: str
    archive_bytes: bytes
    files: tuple[dict[str, Any], ...]
    declared_tools: tuple[str, ...]
    referenced_tools: tuple[str, ...]
    warnings: tuple[dict[str, str], ...]
    model_invocable: bool
    user_invocable: bool
    package_kind: Literal["ordinary", "expert_package"] = "ordinary"
    children: tuple[dict[str, str], ...] = ()

    def package_summary(self) -> dict[str, Any]:
        return {
            "slug": self.name,
            "version": self.version,
            "digest": self.archive_digest,
            "rootPrefix": self.root_prefix,
            "files": [dict(item) for item in self.files],
            "declaredTools": list(self.declared_tools),
            "referencedTools": list(self.referenced_tools),
            "warnings": [dict(item) for item in self.warnings],
            "modelInvocable": self.model_invocable,
            "userInvocable": self.user_invocable,
            "kind": self.package_kind,
            "children": [dict(item) for item in self.children],
        }


def _safe_zip_path(raw: str) -> str:
    value = str(raw or "")
    if not value or "\x00" in value or "\\" in value or value.startswith("/"):
        raise SkillPackageError("unsafe_archive_path", "ZIP contains an unsafe path", file=value)
    normalized = posixpath.normpath(value)
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise SkillPackageError("unsafe_archive_path", "ZIP path escapes the Skill bundle", file=value)
    return normalized.rstrip("/")


def _frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        raise SkillPackageError("missing_frontmatter", "SKILL.md must begin with YAML frontmatter", file="SKILL.md")
    lines = normalized.split("\n")
    end_line = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), -1)
    if end_line < 0:
        raise SkillPackageError("invalid_frontmatter", "SKILL.md frontmatter is not closed", file="SKILL.md")
    try:
        parsed = yaml.safe_load("\n".join(lines[1:end_line])) or {}
    except yaml.YAMLError as exc:
        raise SkillPackageError("invalid_frontmatter", f"Invalid YAML frontmatter: {exc}", file="SKILL.md") from exc
    if not isinstance(parsed, dict):
        raise SkillPackageError("invalid_frontmatter", "SKILL.md frontmatter must be a mapping", file="SKILL.md")
    return parsed, "\n".join(lines[end_line + 1 :]).lstrip("\n")


def _bool_field(meta: dict[str, Any], key: str) -> None:
    if key not in meta:
        return
    value = meta[key]
    if isinstance(value, bool):
        return
    if isinstance(value, str) and value.strip().lower() in {"true", "false", "yes", "no", "on", "off", "1", "0"}:
        return
    raise SkillPackageError("invalid_invocation_policy", f"{key} must be a boolean", file="SKILL.md", field=key)


def _bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "on", "1"}


def validate_skill_zip(content: bytes) -> ValidatedSkillPackage:
    if not content:
        raise SkillPackageError("empty_archive", "The uploaded ZIP is empty")
    if len(content) > MAX_ARCHIVE_BYTES:
        raise SkillPackageError("archive_too_large", f"ZIP exceeds the {MAX_ARCHIVE_BYTES} byte limit")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise SkillPackageError("invalid_zip", "The uploaded file is not a valid ZIP archive") from exc

    entries: list[tuple[zipfile.ZipInfo, str]] = []
    seen: set[str] = set()
    total = 0
    with archive:
        for info in archive.infolist():
            path = _safe_zip_path(info.filename)
            if path.startswith(IGNORED_PREFIXES) or info.is_dir():
                continue
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise SkillPackageError("symlink_not_allowed", "Symbolic links are not allowed", file=path)
            if info.flag_bits & 0x1:
                raise SkillPackageError("encrypted_archive", "Encrypted ZIP entries are not supported", file=path)
            if path in seen:
                raise SkillPackageError("duplicate_archive_path", "ZIP contains duplicate paths", file=path)
            seen.add(path)
            total += info.file_size
            if info.file_size > MAX_FILE_BYTES:
                raise SkillPackageError("file_too_large", f"File exceeds the {MAX_FILE_BYTES} byte limit", file=path)
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise SkillPackageError("suspicious_compression", "ZIP entry has an unsafe compression ratio", file=path)
            entries.append((info, path))
        if len(entries) > MAX_FILES:
            raise SkillPackageError("too_many_files", f"ZIP contains more than {MAX_FILES} files")
        if total > MAX_UNCOMPRESSED_BYTES:
            raise SkillPackageError("expanded_archive_too_large", f"Expanded ZIP exceeds {MAX_UNCOMPRESSED_BYTES} bytes")

        roots = [path for _, path in entries if path == "SKILL.md" or path.endswith("/SKILL.md")]
        if not roots:
            raise SkillPackageError("missing_skill_md", "ZIP does not contain SKILL.md")
        if len(roots) != 1:
            raise SkillPackageError("multiple_skills", "ZIP must contain exactly one Skill", file=", ".join(roots[:5]))
        skill_path = roots[0]
        prefix = skill_path[:-len("SKILL.md")]
        if prefix and "/" in prefix.rstrip("/"):
            raise SkillPackageError("invalid_bundle_structure", "SKILL.md may only be at the root or inside one top-level directory", file=skill_path)
        outside = [path for _, path in entries if prefix and not path.startswith(prefix)]
        if outside:
            raise SkillPackageError("invalid_bundle_structure", "Files exist outside the Skill root directory", file=outside[0])
        try:
            markdown = archive.read(next(info for info, path in entries if path == skill_path)).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SkillPackageError("skill_md_not_utf8", "SKILL.md must be UTF-8", file=skill_path) from exc
        meta, body = _frontmatter(markdown)
        name = str(meta.get("name") or meta.get("slug") or "").strip()
        if not name:
            raise SkillPackageError("missing_metadata", "Skill name is required", file=skill_path, field="name")
        if not SKILL_NAME.fullmatch(name):
            raise SkillPackageError("invalid_skill_name", "Skill name must use DSH kebab-case syntax", file=skill_path, field="name")
        description = str(meta.get("description") or "").strip()
        if not description:
            raise SkillPackageError("missing_metadata", "Skill description is required", file=skill_path, field="description")
        if not body.strip():
            raise SkillPackageError("empty_skill_body", "SKILL.md has no instruction body", file=skill_path)
        for key in ("disable-model-invocation", "user-invocable"):
            _bool_field(meta, key)

        market_meta: dict[str, Any] = {}
        meta_path = f"{prefix}_meta.json"
        if meta_path in seen:
            try:
                parsed_market = json.loads(archive.read(next(info for info, path in entries if path == meta_path)))
                if isinstance(parsed_market, dict):
                    market_meta = parsed_market
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise SkillPackageError("invalid_market_metadata", "_meta.json must contain a UTF-8 JSON object", file=meta_path) from exc
        market_slug = str(market_meta.get("slug") or "").strip()
        if market_slug and market_slug != name:
            raise SkillPackageError("metadata_mismatch", "_meta.json slug does not match SKILL.md name", file=meta_path, field="slug")
        front_version = str(meta.get("version") or "").strip()
        market_version = str(market_meta.get("version") or "").strip()
        metadata_warnings: list[dict[str, str]] = []
        if front_version and market_version and front_version != market_version:
            metadata_warnings.append({
                "code": "version_metadata_mismatch",
                "message": "_meta.json version does not match SKILL.md version; using the package version",
                "packageVersion": market_version,
                "skillVersion": front_version,
            })
        # _meta.json describes the distributed package, so its version is canonical
        # for installs and updates. A stale version inside SKILL.md does not affect DSH execution.
        version = market_version or front_version or "1.0.0"
        if len(version) > 128 or not SKILL_VERSION.fullmatch(version):
            raise SkillPackageError("invalid_version", "Skill version must be valid SemVer", field="version")
        raw_tools = meta.get("tools") or []
        if isinstance(raw_tools, str):
            raw_tools = [raw_tools]
        if not isinstance(raw_tools, list) or any(not isinstance(item, str) for item in raw_tools):
            raise SkillPackageError("invalid_tools", "tools must be a list of tool names", file=skill_path, field="tools")
        declared = tuple(dict.fromkeys(item.strip() for item in raw_tools if item.strip()))
        code_samples = "\n".join(FENCED_CODE.findall(body))
        referenced = tuple(sorted(set(TOOL_REFERENCE.findall(code_samples))))
        undeclared = sorted(set(referenced) - set(declared))
        warnings = tuple(metadata_warnings) + tuple({
            "code": "undeclared_tool_reference",
            "message": f"SKILL.md references undeclared tool '{tool}'",
            "tool": tool,
        } for tool in undeclared)
        manifest = tuple({
            "path": path[len(prefix):] if prefix else path,
            "size": info.file_size,
            "sha256": hashlib.sha256(archive.read(info)).hexdigest(),
        } for info, path in entries)

    return ValidatedSkillPackage(
        name=name,
        display_name=str(meta.get("displayName") or meta.get("display_name") or name).strip()[:256],
        description=description[:2000],
        when_to_use=str(meta.get("whenToUse") or meta.get("when_to_use") or description).strip()[:4000],
        version=version,
        markdown=body,
        metadata=meta,
        market_metadata=market_meta,
        root_prefix=prefix,
        archive_digest=hashlib.sha256(content).hexdigest(),
        archive_bytes=content,
        files=manifest,
        declared_tools=declared,
        referenced_tools=referenced,
        warnings=warnings,
        model_invocable=not _bool_value(meta.get("disable-model-invocation"), False),
        user_invocable=_bool_value(meta.get("user-invocable"), True),
    )
