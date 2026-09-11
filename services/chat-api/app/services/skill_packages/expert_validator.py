from __future__ import annotations

import hashlib
import io
import json
import posixpath
import stat
import zipfile
from dataclasses import replace
from typing import Any

from .validator import (
    MAX_ARCHIVE_BYTES,
    MAX_COMPRESSION_RATIO,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_UNCOMPRESSED_BYTES,
    SKILL_NAME,
    SKILL_VERSION,
    SkillPackageError,
    ValidatedSkillPackage,
    _bool_value,
    _frontmatter,
    _safe_zip_path,
    validate_skill_zip,
)


EXPERT_PACKAGE_TYPE = "skillhub-expert-package"
MAX_EXPERT_INSTRUCTION_BYTES = 100_000


def is_expert_package(content: bytes) -> bool:
    if not content or len(content) > MAX_ARCHIVE_BYTES:
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = {_safe_zip_path(item.filename) for item in archive.infolist() if not item.is_dir()}
            has_expert_shape = (
                any(name.startswith("skillsets/") and name.endswith(".md") for name in names)
                and any(name.startswith("skills/") and name.endswith(".zip") for name in names)
            )
            if "manifest.json" not in names:
                # Keep malformed expert bundles on the expert validation path so
                # the UI can explain that manifest.json is missing instead of
                # reporting an unrelated missing SKILL.md error.
                return has_expert_shape
            try:
                manifest = json.loads(archive.read("manifest.json"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                manifest = None
            return (
                isinstance(manifest, dict) and manifest.get("type") == EXPERT_PACKAGE_TYPE
            ) or has_expert_shape
    except (SkillPackageError, zipfile.BadZipFile, OSError):
        return False


def validate_expert_package(content: bytes) -> ValidatedSkillPackage:
    if not content:
        raise SkillPackageError("empty_archive", "The uploaded ZIP is empty")
    if len(content) > MAX_ARCHIVE_BYTES:
        raise SkillPackageError("archive_too_large", f"ZIP exceeds the {MAX_ARCHIVE_BYTES} byte limit")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise SkillPackageError("invalid_zip", "The uploaded file is not a valid ZIP archive") from exc

    with archive:
        file_names = _validated_outer_entries(archive)
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except KeyError as exc:
            raise SkillPackageError("missing_expert_manifest", "Expert package does not contain manifest.json") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SkillPackageError("invalid_expert_manifest", "Expert package manifest.json is invalid") from exc
        if not isinstance(manifest, dict) or manifest.get("type") != EXPERT_PACKAGE_TYPE:
            raise SkillPackageError("invalid_expert_manifest", "Unsupported expert package manifest type", field="type")

        slug = str(manifest.get("slug") or "").strip()
        if not SKILL_NAME.fullmatch(slug):
            raise SkillPackageError("invalid_skill_name", "Expert package slug must use DSH kebab-case syntax", file="manifest.json", field="slug")
        descriptor_path = f"skillsets/{slug}.md"
        descriptor_candidates = [name for name in file_names if name.startswith("skillsets/") and name.endswith(".md")]
        if descriptor_path not in descriptor_candidates:
            raise SkillPackageError("missing_expert_descriptor", "Expert package does not contain its skillset descriptor", file=descriptor_path)
        if len(descriptor_candidates) != 1:
            raise SkillPackageError("invalid_bundle_structure", "Expert package must contain exactly one skillset descriptor", file="skillsets")
        try:
            descriptor_text = archive.read(descriptor_path).decode("utf-8")
        except KeyError as exc:
            raise SkillPackageError("missing_expert_descriptor", "Expert package does not contain its skillset descriptor", file=descriptor_path) from exc
        except UnicodeDecodeError as exc:
            raise SkillPackageError("skill_md_not_utf8", "Expert package descriptor must be UTF-8", file=descriptor_path) from exc
        try:
            descriptor_meta, descriptor_body = _frontmatter(descriptor_text)
        except SkillPackageError as exc:
            raise SkillPackageError(exc.code, exc.message, file=descriptor_path, field=exc.field) from exc
        if str(descriptor_meta.get("name") or "").strip() != slug:
            raise SkillPackageError("expert_descriptor_name_mismatch", "Expert descriptor name does not match manifest slug", file=descriptor_path, field="name")
        if not descriptor_body.strip():
            raise SkillPackageError("empty_skill_body", "Expert package descriptor has no orchestration body", file=descriptor_path)

        child_slugs = _manifest_child_slugs(manifest)
        if not child_slugs:
            raise SkillPackageError("missing_expert_children", "Expert package does not declare child Skills", file="manifest.json", field="skillSlugs")
        orchestration = descriptor_meta.get("orchestration")
        declared_children = orchestration.get("children") if isinstance(orchestration, dict) else None
        if not isinstance(declared_children, list) or not declared_children:
            raise SkillPackageError("missing_expert_children", "Expert descriptor does not declare orchestration children", file=descriptor_path, field="orchestration.children")
        if [str(item) for item in declared_children] != child_slugs:
            raise SkillPackageError("expert_children_mismatch", "Expert descriptor children do not match manifest", file=descriptor_path, field="orchestration.children")
        expected_child_paths = {f"skills/{child_slug}.zip" for child_slug in child_slugs}
        actual_child_paths = {name for name in file_names if name.startswith("skills/") and name.endswith(".zip")}
        missing_child_paths = expected_child_paths - actual_child_paths
        if missing_child_paths:
            raise SkillPackageError("missing_expert_child", "Expert package is missing a child Skill ZIP", file=sorted(missing_child_paths)[0])
        if actual_child_paths - expected_child_paths:
            raise SkillPackageError("expert_children_mismatch", "Expert package child ZIPs do not match manifest", file="skills")

        child_packages: list[ValidatedSkillPackage] = []
        for child_slug in child_slugs:
            child_path = f"skills/{child_slug}.zip"
            try:
                child_content = archive.read(child_path)
            except KeyError as exc:
                raise SkillPackageError("missing_expert_child", "Expert package is missing a child Skill ZIP", file=child_path) from exc
            try:
                child = validate_skill_zip(child_content)
            except SkillPackageError as exc:
                nested_file = f"{child_path}!/{exc.file}" if exc.file else child_path
                raise SkillPackageError(exc.code, exc.message, file=nested_file, field=exc.field) from exc
            if child.name != child_slug:
                child = replace(child, name=child_slug, warnings=({
                    "code": "expert_child_name_mismatch",
                    "message": "Child Skill name differs from its expert package slug; using the package slug",
                    "declaredName": child_slug,
                    "skillName": child.name,
                }, *child.warnings))
            child_packages.append(child)

    descriptor_metadata = descriptor_meta.get("metadata") if isinstance(descriptor_meta.get("metadata"), dict) else {}
    markdown = _expert_markdown(
        name=str(manifest.get("displayName") or descriptor_metadata.get("display_name") or slug).strip(),
        descriptor=descriptor_body,
        children=child_packages,
    )
    if len(markdown.encode("utf-8")) > MAX_EXPERT_INSTRUCTION_BYTES:
        raise SkillPackageError("expert_instructions_too_large", "Combined expert package instructions exceed the runtime limit")

    normalized_files = _normalized_files(manifest, descriptor_text, child_packages)
    if len(normalized_files) > MAX_FILES:
        raise SkillPackageError("too_many_files", f"Expert package contains more than {MAX_FILES} expanded files")
    if sum(len(value) for value in normalized_files.values()) > MAX_UNCOMPRESSED_BYTES:
        raise SkillPackageError("expanded_archive_too_large", f"Expanded expert package exceeds {MAX_UNCOMPRESSED_BYTES} bytes")
    normalized_archive = _deterministic_zip(normalized_files)
    files = tuple({
        "path": path,
        "size": len(value),
        "sha256": hashlib.sha256(value).hexdigest(),
    } for path, value in sorted(normalized_files.items()))
    warnings = tuple(
        {**warning, "childSlug": child.name}
        for child in child_packages
        for warning in child.warnings
    )
    version = str(descriptor_meta.get("version") or manifest.get("version") or "1.0.0").strip()
    if len(version) > 128 or not SKILL_VERSION.fullmatch(version):
        raise SkillPackageError("invalid_version", "Expert package version must be valid SemVer", file=descriptor_path, field="version")
    description = str(manifest.get("summary") or descriptor_meta.get("description") or "").strip()
    if not description:
        raise SkillPackageError("missing_metadata", "Expert package description is required", file="manifest.json", field="summary")

    return ValidatedSkillPackage(
        name=slug,
        display_name=str(manifest.get("displayName") or slug).strip()[:256],
        description=description[:2000],
        when_to_use=str(descriptor_meta.get("description") or description).strip()[:4000],
        version=version,
        markdown=markdown,
        metadata=descriptor_meta,
        market_metadata=manifest,
        root_prefix="",
        archive_digest=hashlib.sha256(normalized_archive).hexdigest(),
        archive_bytes=normalized_archive,
        files=files,
        declared_tools=tuple(dict.fromkeys(tool for child in child_packages for tool in child.declared_tools)),
        referenced_tools=tuple(sorted(set(tool for child in child_packages for tool in child.referenced_tools))),
        warnings=warnings,
        model_invocable=not _bool_value(descriptor_meta.get("disable-model-invocation"), False),
        user_invocable=_bool_value(descriptor_meta.get("user-invocable"), True),
        package_kind="expert_package",
        children=tuple({
            "slug": child.name,
            "name": child.display_name,
            "description": child.description,
            "version": child.version,
        } for child in child_packages),
    )


def _validated_outer_entries(archive: zipfile.ZipFile) -> list[str]:
    names: list[str] = []
    total = 0
    for info in archive.infolist():
        path = _safe_zip_path(info.filename)
        if info.is_dir():
            continue
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise SkillPackageError("symlink_not_allowed", "Symbolic links are not allowed", file=path)
        if info.flag_bits & 0x1:
            raise SkillPackageError("encrypted_archive", "Encrypted ZIP entries are not supported", file=path)
        if info.file_size > MAX_FILE_BYTES:
            raise SkillPackageError("file_too_large", f"File exceeds the {MAX_FILE_BYTES} byte limit", file=path)
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise SkillPackageError("suspicious_compression", "ZIP entry has an unsafe compression ratio", file=path)
        total += info.file_size
        names.append(path)
    if len(names) > MAX_FILES:
        raise SkillPackageError("too_many_files", f"ZIP contains more than {MAX_FILES} files")
    if total > MAX_UNCOMPRESSED_BYTES:
        raise SkillPackageError("expanded_archive_too_large", f"Expanded ZIP exceeds {MAX_UNCOMPRESSED_BYTES} bytes")
    if len(names) != len(set(names)):
        raise SkillPackageError("duplicate_archive_path", "ZIP contains duplicate paths")
    return names


def _manifest_child_slugs(manifest: dict[str, Any]) -> list[str]:
    values = manifest.get("skillSlugs")
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise SkillPackageError("invalid_expert_manifest", "skillSlugs must be a list of Skill names", file="manifest.json", field="skillSlugs")
    result = [item.strip() for item in values]
    if any(not SKILL_NAME.fullmatch(item) for item in result) or len(result) != len(set(result)):
        raise SkillPackageError("invalid_expert_manifest", "skillSlugs contains invalid or duplicate names", file="manifest.json", field="skillSlugs")
    detailed = manifest.get("skills")
    if isinstance(detailed, list):
        detailed_slugs = [str(item.get("slug") or "").strip() for item in detailed if isinstance(item, dict)]
        if detailed_slugs != result:
            raise SkillPackageError("expert_children_mismatch", "manifest skills do not match skillSlugs", file="manifest.json", field="skills")
    return result


def _expert_markdown(*, name: str, descriptor: str, children: list[ValidatedSkillPackage]) -> str:
    directory = "\n".join(
        f"- `{child.name}` ({child.display_name}): {child.description}" for child in children
    )
    bodies = "\n\n".join(
        f"<child_skill name=\"{child.name}\" resource_base=\"children/{child.name}\">\n"
        f"# {child.display_name}\n\n{child.markdown.strip()}\n</child_skill>"
        for child in children
    )
    return f"""# {name}

## Expert package orchestration

The orchestration instructions in this section are authoritative. Select and combine the internal child Skills only as these instructions direct. The child Skills are package-internal capabilities and are not independent catalog entries. Do not invoke a child name through the DSH Skill loader; its instructions are already loaded below, so apply them directly within this expert package.

{descriptor.strip()}

## Internal child Skill directory

{directory}

## Internal child Skill instructions

{bodies}
""".strip()


def _normalized_files(
    manifest: dict[str, Any], descriptor_text: str, children: list[ValidatedSkillPackage]
) -> dict[str, bytes]:
    files: dict[str, bytes] = {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        "skillset.md": descriptor_text.encode("utf-8"),
    }
    for child in children:
        with zipfile.ZipFile(io.BytesIO(child.archive_bytes)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                path = _safe_zip_path(info.filename)
                if child.root_prefix and not path.startswith(child.root_prefix):
                    continue
                relative = path[len(child.root_prefix):] if child.root_prefix else path
                target = posixpath.join("children", child.name, relative)
                if target in files:
                    raise SkillPackageError("duplicate_archive_path", "Expert package contains duplicate normalized paths", file=target)
                files[target] = archive.read(info)
    return files


def _deterministic_zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content)
    return output.getvalue()
