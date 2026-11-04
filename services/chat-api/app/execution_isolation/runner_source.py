"""Python entry point for code execution in an isolated task container."""

from __future__ import annotations


RUNNER_SOURCE = r'''
import importlib.util
import inspect
import json
import os
import socket
import sys

def _deny_network(*args, **kwargs):
    raise RuntimeError("network access is disabled for this execution")

plugin_path, stdin_path = sys.argv[1], sys.argv[2]
with open(stdin_path, "r", encoding="utf-8") as stream:
    payload = json.load(stream)
context = payload.get("context") or {}
if not context.get("allow_network"):
    socket.socket = _deny_network
    socket.create_connection = _deny_network

# The container has a read-only root, a private writable task workspace, and
# an optional read-only Skill mount. Filesystem isolation belongs to Docker;
# Python-level open hooks also block legitimate package and tool reads.
os.chdir(context.get("work_dir") or "/job/work")
dependency_dir = os.path.join(context.get("work_dir") or "/job/work", ".dependencies", "python")
if os.path.isdir(dependency_dir):
    sys.path.insert(0, dependency_dir)
spec = importlib.util.spec_from_file_location("movo_task_plugin", plugin_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
run = getattr(module, "run", None)
if not callable(run):
    raise RuntimeError("code execution must define run(inputs, context)")
inputs = payload.get("inputs") or {}
module.skill_dir = context.get("skill_dir") or ""
signature = inspect.signature(run)
for arguments in ((inputs, context), (inputs,), ()):
    try:
        signature.bind(*arguments)
    except TypeError:
        continue
    result = run(*arguments)
    break
else:
    raise RuntimeError("run() must accept zero, one, or two positional arguments")
if result is None:
    result = {}
if not isinstance(result, dict):
    raise RuntimeError("run(inputs, context) must return a dict")
print(json.dumps(result, ensure_ascii=False))
'''.strip()


def runner_source(*, container_isolated: bool = False) -> str:
    if not container_isolated:
        from .runner_source_legacy import RUNNER_SOURCE as LEGACY_RUNNER_SOURCE
        return LEGACY_RUNNER_SOURCE
    return RUNNER_SOURCE
