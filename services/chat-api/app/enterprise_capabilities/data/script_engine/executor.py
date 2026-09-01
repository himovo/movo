from __future__ import annotations

import asyncio
import json
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, List, Tuple

from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.data.script_engine.base import BaseExecutor
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityInputs
from app.infrastructure.request_context import get_request_context
from app.enterprise_capabilities.data.script_engine.message_ops import last_user_text_from_dict_messages
from app.utils.oss_uploader import AliyunOSSUploader
from app.enterprise_capabilities.data.script_engine.error_summary import execution_error_summary
from app.enterprise_capabilities.data.script_engine.artifact_export import export_script_artifacts


class ScriptPluginExecutor(BaseExecutor):
    _CAPABILITY = "file.run_script_plugin"
    _MAX_PLUGIN_BYTES = 256 * 1024
    _MAX_STDOUT_BYTES = 2 * 1024 * 1024
    _TIMEOUT_SECONDS = 60

    def can_handle(self, node: CapabilityTask) -> bool:
        capability_id = str((node.meta or {}).get("capability_id") or "").strip().lower()
        return capability_id == self._CAPABILITY

    async def execute(
        self,
        *,
        runtime: Any,
        task_id: str,
        run_id: str,
        node: CapabilityTask,
        inputs: CapabilityInputs,
        skills: Dict[str, Any],
    ) -> AsyncIterator[Tuple[Dict[str, Any], Dict[str, Any]]]:
        yield {"type": "skill_step_started", "content": f"Run script plugin for {node.node_id}"}, {}
        try:
            artifacts = await asyncio.to_thread(
                self._run_plugin,
                node=node,
                inputs=inputs,
                task_id=task_id,
                run_id=run_id,
            )
        except Exception as exc:
            error = execution_error_summary(exc)
            yield {
                "type": "runtime_status",
                "content": {
                    "node_id": node.node_id,
                    "state": "script_plugin_failed",
                    "error": error,
                },
            }, {}
            yield {
                "type": "subagent_done",
                "content": {
                    "subagent_id": "",
                    "node_id": node.node_id,
                    "status": "failed_plugin",
                    "error": error,
                },
            }, {}
            return

        documents = list(artifacts.get("documents") or [])
        images = list(artifacts.get("images") or [])
        yield {
            "type": "runtime_status",
            "content": {
                "node_id": node.node_id,
                "state": "script_plugin_completed",
                "document_count": len(documents),
                "image_count": len(images),
            },
        }, {}
        yield {
            "type": "subagent_done",
            "content": {
                "subagent_id": "",
                "node_id": node.node_id,
                "status": "succeeded",
            },
        }, artifacts

    def _run_plugin(self, *, node: CapabilityTask, inputs: CapabilityInputs, task_id: str, run_id: str) -> Dict[str, Any]:
        semantic_config = (node.meta or {}).get("semantic_config")
        config = dict(semantic_config or {}) if isinstance(semantic_config, dict) else {}
        plugin_code = str(
            config.get("pluginCode")
            or config.get("scriptCode")
            or config.get("code")
            or config.get("python")
            or ""
        )
        if not plugin_code.strip():
            raise ValueError("script_plugin node requires businessConfig.pluginCode")
        if len(plugin_code.encode("utf-8")) > self._MAX_PLUGIN_BYTES:
            raise ValueError("script plugin code is too large")

        user_id = str((inputs.output_spec or {}).get("user_id") or (inputs.output_spec or {}).get("userId") or "").strip()
        if not user_id:
            user_id = str(get_request_context().get("user_id") or "anonymous")

        with tempfile.TemporaryDirectory(prefix="askai_script_plugin_") as tmp:
            work_dir = Path(tmp)
            input_dir = work_dir / "inputs"
            output_dir = work_dir / "out"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            files = self._materialize_input_files(input_dir=input_dir, node=node, inputs=inputs)
            plugin_path = work_dir / "plugin.py"
            runner_path = work_dir / "runner.py"
            stdin_path = work_dir / "stdin.json"
            plugin_path.write_text(plugin_code, encoding="utf-8")
            runner_path.write_text(self._runner_source(), encoding="utf-8")

            payload = {
                "inputs": {
                    "files": files,
                    "artifacts": dict((inputs.output_spec or {}).get("graph_artifacts") or {}),
                    "predecessor_artifacts": self._predecessor_artifacts(node=node, inputs=inputs),
                    "input_artifacts": self._flatten_predecessors(node=node, inputs=inputs),
                    "selected": self._build_selected_inputs(files=files, node=node, inputs=inputs, config=config),
                    "messages": inputs.raw_messages or [],
                    "user_text": last_user_text_from_dict_messages(inputs.raw_messages or inputs.messages or []),
                    "output_spec": inputs.output_spec or {},
                },
                "context": {
                    "task_id": task_id,
                    "run_id": run_id,
                    "node_id": node.node_id,
                    "node_goal": getattr(node, "goal", "") or "",
                    "config": config,
                    "work_dir": str(work_dir),
                    "input_dir": str(input_dir),
                    "output_dir": str(output_dir),
                },
            }
            stdin_path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")

            started = time.monotonic()
            completed = subprocess.run(
                [sys.executable, "-I", str(runner_path), str(plugin_path), str(stdin_path)],
                cwd=str(work_dir),
                env=self._safe_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self._TIMEOUT_SECONDS,
                preexec_fn=self._limit_child_process,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout = (completed.stdout or "")[: self._MAX_STDOUT_BYTES]
            stderr = (completed.stderr or "")[:8000]
            if completed.returncode != 0:
                raise RuntimeError(f"script plugin exited with code {completed.returncode}: {stderr or stdout}")
            result = self._parse_stdout(stdout)
            return self._build_artifacts(
                result=result,
                output_dir=output_dir,
                user_id=user_id,
                duration_ms=duration_ms,
                stderr=stderr,
            )

    def _materialize_input_files(self, *, input_dir: Path, node: CapabilityTask, inputs: CapabilityInputs) -> List[Dict[str, Any]]:
        uploader = AliyunOSSUploader()
        candidates = self._collect_file_candidates(node=node, inputs=inputs)
        files: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for idx, item in enumerate(candidates[:80]):
            if not isinstance(item, dict):
                continue
            object_path = str(item.get("object_path") or "").strip()
            local_path = str(item.get("local_path") or item.get("path") or "").strip()
            marker = object_path or local_path or str(item.get("url") or item.get("signed_url") or "")
            if not marker or marker in seen:
                continue
            seen.add(marker)
            filename = str(item.get("filename") or Path(object_path or local_path or f"input_{idx}").name).strip()
            if not filename:
                filename = f"input_{idx}"
            target = input_dir / self._safe_filename(filename, fallback=f"input_{idx}")
            try:
                if object_path:
                    target.write_bytes(uploader.read_bytes(object_path))
                elif local_path and Path(local_path).exists():
                    shutil.copyfile(local_path, target)
                else:
                    continue
            except Exception:
                continue
            files.append(
                {
                    **{k: v for k, v in item.items() if k not in {"local_path", "path"}},
                    "filename": filename,
                    "local_path": str(target),
                    "size": target.stat().st_size,
                }
            )
        return files

    def _collect_file_candidates(self, *, node: CapabilityTask, inputs: CapabilityInputs) -> List[Dict[str, Any]]:
        roots: List[Any] = []
        output_spec = inputs.output_spec if isinstance(inputs.output_spec, dict) else {}
        roots.append(output_spec)
        roots.append(output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {})
        roots.append(output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {})
        roots.append(self._predecessor_artifacts(node=node, inputs=inputs))
        roots.append(self._flatten_predecessors(node=node, inputs=inputs))
        out: List[Dict[str, Any]] = []
        for root in roots:
            out.extend(self._walk_file_dicts(root))
        return out

    def _walk_file_dicts(self, value: Any, *, depth: int = 0) -> List[Dict[str, Any]]:
        if depth > 8:
            return []
        if isinstance(value, dict):
            if any(str(value.get(k) or "").strip() for k in ("object_path", "local_path", "path")) and (
                value.get("filename") or value.get("object_path") or value.get("local_path") or value.get("path")
            ):
                return [dict(value)]
            out: List[Dict[str, Any]] = []
            for nested in value.values():
                out.extend(self._walk_file_dicts(nested, depth=depth + 1))
            return out
        if isinstance(value, list):
            out: List[Dict[str, Any]] = []
            for item in value[:300]:
                out.extend(self._walk_file_dicts(item, depth=depth + 1))
            return out
        return []

    @staticmethod
    def _predecessor_artifacts(*, node: CapabilityTask, inputs: CapabilityInputs) -> Dict[str, Any]:
        graph_artifacts = dict((inputs.output_spec or {}).get("graph_artifacts") or {})
        return {
            dep_id: graph_artifacts.get(dep_id)
            for dep_id in list(node.depends_on or [])
            if isinstance(graph_artifacts.get(dep_id), dict)
        }

    def _flatten_predecessors(self, *, node: CapabilityTask, inputs: CapabilityInputs) -> Dict[str, Any]:
        flattened: Dict[str, Any] = {}
        for artifact in self._predecessor_artifacts(node=node, inputs=inputs).values():
            if not isinstance(artifact, dict):
                continue
            for key, value in artifact.items():
                if not str(key).startswith("_"):
                    flattened.setdefault(str(key), value)
        return flattened

    def _build_selected_inputs(
        self,
        *,
        files: List[Dict[str, Any]],
        node: CapabilityTask,
        inputs: CapabilityInputs,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_types = config.get("selectedInputTypes") or config.get("inputTypes") or [
            "files",
            "documents",
            "images",
            "urls",
            "texts",
            "tables",
            "data",
        ]
        selected_types = {str(item).strip() for item in raw_types if str(item).strip()} if isinstance(raw_types, list) else {"files"}
        roots = self._selected_roots(node=node, inputs=inputs, source=str(config.get("selectedInputSource") or config.get("inputSource") or "all"))
        selected_files = self._filter_files_by_roots(files, roots) if "files" in selected_types else []
        selected = {
            "files": selected_files,
            "documents": self._collect_documents(roots) if "documents" in selected_types else [],
            "images": self._collect_typed_files(roots, kind="images") if "images" in selected_types else [],
            "urls": self._collect_urls(roots) if "urls" in selected_types else [],
            "texts": self._collect_texts(roots) if "texts" in selected_types else [],
            "tables": self._collect_tables(roots) if "tables" in selected_types else [],
            "data": self._collect_data(roots) if "data" in selected_types else {},
        }
        selected["summary"] = {
            "files": len(selected["files"]),
            "documents": len(selected["documents"]),
            "images": len(selected["images"]),
            "urls": len(selected["urls"]),
            "texts": len(selected["texts"]),
            "tables": len(selected["tables"]),
            "data_keys": list(selected["data"].keys())[:50] if isinstance(selected["data"], dict) else [],
        }
        return selected

    def _filter_files_by_roots(self, files: List[Dict[str, Any]], roots: List[Any]) -> List[Dict[str, Any]]:
        root_candidates: List[Dict[str, Any]] = []
        for root in roots:
            root_candidates.extend(self._walk_file_dicts(root))
        if not root_candidates:
            return list(files)
        markers: set[str] = set()
        for item in root_candidates:
            for key in ("object_path", "filename", "url", "signed_url"):
                value = str(item.get(key) or "").strip()
                if value:
                    markers.add(value)
                    markers.add(Path(value.replace("\\", "/")).name)
        filtered: List[Dict[str, Any]] = []
        for item in files:
            values = {
                str(item.get("object_path") or "").strip(),
                str(item.get("filename") or "").strip(),
                str(item.get("url") or "").strip(),
                str(item.get("signed_url") or "").strip(),
            }
            values.update(Path(value.replace("\\", "/")).name for value in list(values) if value)
            if any(value and value in markers for value in values):
                filtered.append(item)
        return filtered

    def _selected_roots(self, *, node: CapabilityTask, inputs: CapabilityInputs, source: str) -> List[Any]:
        output_spec = inputs.output_spec if isinstance(inputs.output_spec, dict) else {}
        predecessor = self._predecessor_artifacts(node=node, inputs=inputs)
        flattened = self._flatten_predecessors(node=node, inputs=inputs)
        roots: List[Any] = []
        token = source.strip().lower()
        if token in {"uploads", "uploaded", "files"}:
            roots.extend([output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}, output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}])
        elif token in {"predecessors", "upstream"}:
            roots.extend([predecessor, flattened])
        else:
            roots.extend([output_spec, output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}, output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}, predecessor, flattened])
        return roots

    def _collect_documents(self, roots: List[Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in self._walk_dicts(roots):
            keys = set(item.keys())
            if keys & {"markdown", "text", "content", "filename", "object_path"}:
                filename = str(item.get("filename") or item.get("title") or item.get("name") or "").strip()
                content_type = str(item.get("content_type") or item.get("mime_type") or "").lower()
                if filename.lower().endswith((".doc", ".docx", ".pdf", ".txt", ".md")) or "document" in content_type or item.get("markdown") or item.get("text"):
                    marker = str(item.get("object_path") or item.get("url") or item.get("signed_url") or filename or item.get("markdown") or item.get("text") or "")[:500]
                    if marker in seen:
                        continue
                    seen.add(marker)
                    out.append({
                        "filename": filename,
                        "title": str(item.get("title") or filename),
                        "markdown": str(item.get("markdown") or "")[:200000],
                        "text": str(item.get("text") or item.get("content") or "")[:200000],
                        "object_path": item.get("object_path"),
                        "url": item.get("url") or item.get("signed_url"),
                    })
        return out[:80]

    def _collect_typed_files(self, roots: List[Any], *, kind: str) -> List[Dict[str, Any]]:
        image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in self._walk_dicts(roots):
            filename = str(item.get("filename") or item.get("name") or item.get("title") or item.get("object_path") or item.get("url") or "").strip()
            content_type = str(item.get("content_type") or item.get("mime_type") or "").lower()
            item_type = str(item.get("type") or item.get("kind") or "").lower()
            suffix = Path(filename).suffix.lower()
            if kind == "images" and (content_type.startswith("image/") or item_type in {"image", "img", "picture"} or suffix in image_exts):
                marker = str(item.get("object_path") or item.get("url") or item.get("signed_url") or filename)
                if marker in seen:
                    continue
                seen.add(marker)
                out.append(dict(item))
        return out[:200]

    def _collect_urls(self, roots: List[Any]) -> List[str]:
        urls: List[str] = []
        seen: set[str] = set()
        for value in self._walk_values(roots):
            candidates: List[str] = []
            if isinstance(value, str):
                candidates.extend(re.findall(r"https?://[^\s<>\]\)\"']+", value))
            elif isinstance(value, dict):
                for key in ("url", "signed_url", "source_url", "href"):
                    raw = str(value.get(key) or "")
                    if raw.startswith(("http://", "https://")):
                        candidates.append(raw)
            for url in candidates:
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
        return urls[:500]

    def _collect_texts(self, roots: List[Any]) -> List[str]:
        out: List[str] = []
        seen: set[str] = set()
        for item in self._walk_dicts(roots):
            for key in ("markdown", "text", "content", "summary"):
                raw = item.get(key)
                if isinstance(raw, str) and raw.strip():
                    marker = raw[:500]
                    if marker in seen:
                        continue
                    seen.add(marker)
                    out.append(raw[:200000])
        return out[:80]

    def _collect_tables(self, roots: List[Any]) -> List[Any]:
        out: List[Any] = []
        for item in self._walk_dicts(roots):
            for key in ("tables", "table", "rows", "sheets"):
                value = item.get(key)
                if isinstance(value, (list, dict)) and value:
                    out.append(value)
        return out[:80]

    def _collect_data(self, roots: List[Any]) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for idx, root in enumerate(roots):
            if isinstance(root, dict):
                for key, value in root.items():
                    if str(key).startswith("_"):
                        continue
                    if key not in data and not self._looks_like_large_text_or_file(value):
                        data[str(key)] = value
            elif isinstance(root, list):
                data.setdefault(f"items_{idx}", root[:50])
        return data

    def _looks_like_large_text_or_file(self, value: Any) -> bool:
        if isinstance(value, str):
            return len(value) > 20000
        if isinstance(value, dict):
            return any(k in value for k in ("local_path", "path", "object_path", "markdown"))
        return False

    def _walk_dicts(self, value: Any, *, depth: int = 0) -> List[Dict[str, Any]]:
        if depth > 8:
            return []
        if isinstance(value, dict):
            out = [value]
            for nested in value.values():
                out.extend(self._walk_dicts(nested, depth=depth + 1))
            return out
        if isinstance(value, list):
            out: List[Dict[str, Any]] = []
            for item in value[:300]:
                out.extend(self._walk_dicts(item, depth=depth + 1))
            return out
        return []

    def _walk_values(self, value: Any, *, depth: int = 0) -> List[Any]:
        if depth > 8:
            return []
        out = [value]
        if isinstance(value, dict):
            for nested in value.values():
                out.extend(self._walk_values(nested, depth=depth + 1))
        elif isinstance(value, list):
            for item in value[:300]:
                out.extend(self._walk_values(item, depth=depth + 1))
        return out

    def _build_artifacts(
        self,
        *,
        result: Dict[str, Any],
        output_dir: Path,
        user_id: str,
        duration_ms: int,
        stderr: str,
    ) -> Dict[str, Any]:
        raw_artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
        if not raw_artifacts and isinstance(result.get("files"), list):
            raw_artifacts = result.get("files") or []
        exported = export_script_artifacts(
            raw_artifacts=raw_artifacts,
            output_dir=output_dir,
            user_id=user_id,
        )
        documents = exported["documents"]
        images = exported["images"]

        logs = result.get("logs") if isinstance(result.get("logs"), list) else []
        plugin_result = {
            "data": result.get("data") if isinstance(result, dict) else {},
            "logs": [str(item)[:1000] for item in logs[:50]],
            "duration_ms": duration_ms,
            "stderr": stderr[:2000],
        }
        artifacts: Dict[str, Any] = {
            "plugin_result": plugin_result,
            "documents": documents,
            "images": images,
            "exported_file": {"documents": documents, "images": images} if documents or images else {},
        }
        return artifacts

    @staticmethod
    def _parse_stdout(stdout: str) -> Dict[str, Any]:
        text = str(stdout or "").strip()
        if not text:
            return {}
        last_line = text.splitlines()[-1].strip()
        try:
            parsed = json.loads(last_line)
        except Exception as exc:
            raise ValueError("script plugin must print one JSON object") from exc
        if not isinstance(parsed, dict):
            raise ValueError("script plugin JSON output must be an object")
        return parsed

    @staticmethod
    def _safe_filename(value: str, *, fallback: str) -> str:
        token = Path(str(value or "").replace("\\", "/")).name.strip()
        token = "".join(ch if ch.isalnum() or ch in "._- ()[]{}" else "_" for ch in token)
        return token[:180] or fallback

    @staticmethod
    def _safe_env() -> Dict[str, str]:
        allowed = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
        }
        return {k: v for k, v in allowed.items() if v}

    @staticmethod
    def _limit_child_process() -> None:
        limits = [
            (resource.RLIMIT_CPU, (60, 65)),
            (resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024)),
            (resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024)),
        ]
        for limit, value in limits:
            try:
                resource.setrlimit(limit, value)
            except Exception:
                continue

    @staticmethod
    def _runner_source() -> str:
        return textwrap.dedent(
            r'''
            import importlib.util
            import builtins
            import io
            import json
            import os
            import socket
            import sys
            import sysconfig

            def _deny_network(*args, **kwargs):
                raise RuntimeError("network access is disabled in script_plugin")

            socket.socket = _deny_network
            socket.create_connection = _deny_network

            plugin_path, stdin_path = sys.argv[1], sys.argv[2]
            with open(stdin_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            spec = importlib.util.spec_from_file_location("askai_user_plugin", plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            run = getattr(module, "run", None)
            if not callable(run):
                raise RuntimeError("script plugin must define run(inputs, context)")

            context = payload.get("context") or {}
            work_dir = os.path.realpath(str(context.get("work_dir") or ""))
            _open = builtins.open
            _io_open = io.open
            _os_open = os.open
            package_roots = set()
            for key in ("purelib", "platlib"):
                value = sysconfig.get_paths().get(key)
                if value:
                    package_roots.add(os.path.realpath(value))

            def _is_write_mode(mode):
                text = str(mode or "r")
                return any(ch in text for ch in ("w", "a", "x", "+"))

            def _check_path(path, *, write=False):
                if not work_dir:
                    return
                raw = os.fspath(path)
                if not raw:
                    return
                if not os.path.isabs(raw):
                    raw = os.path.join(work_dir, raw)
                real = os.path.realpath(raw)
                if real != work_dir and not real.startswith(work_dir + os.sep):
                    if not write and any(real == root or real.startswith(root + os.sep) for root in package_roots):
                        return
                    raise PermissionError("script_plugin file access is limited to work_dir")

            def _guarded_open(file, *args, **kwargs):
                mode = args[0] if args else kwargs.get("mode", "r")
                _check_path(file, write=_is_write_mode(mode))
                return _open(file, *args, **kwargs)

            def _guarded_io_open(file, *args, **kwargs):
                mode = args[0] if args else kwargs.get("mode", "r")
                _check_path(file, write=_is_write_mode(mode))
                return _io_open(file, *args, **kwargs)

            def _guarded_os_open(file, flags, mode=0o777, *, dir_fd=None):
                if dir_fd is None:
                    write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                    _check_path(file, write=write)
                return _os_open(file, flags, mode, dir_fd=dir_fd)

            builtins.open = _guarded_open
            io.open = _guarded_io_open
            os.open = _guarded_os_open
            result = run(payload.get("inputs") or {}, context)
            if result is None:
                result = {}
            if not isinstance(result, dict):
                raise RuntimeError("run(inputs, context) must return a dict")
            print(json.dumps(result, ensure_ascii=False))
            '''
        ).strip()
