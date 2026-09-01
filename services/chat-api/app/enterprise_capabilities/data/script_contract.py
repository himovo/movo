"""Compile DSH-friendly Python into the mature sandbox plugin contract."""

from __future__ import annotations

import ast
import textwrap


def compile_script_plugin(code: str) -> str:
    """Accept either ``run(inputs, context)`` plugins or ordinary Python.

    Ordinary Python is wrapped without changing the sandbox. Its stdout is
    returned as governed JSON data, which gives DSH a deterministic result
    instead of failing the legacy plugin entry-point protocol.
    """
    source = str(code or "").strip()
    if not source:
        raise ValueError("script code is empty")
    tree = ast.parse(source, mode="exec")
    if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run" for node in tree.body):
        return source
    indented = textwrap.indent(source, "    ")
    return (
        "def run(inputs, context):\n"
        "    import io as _io\n"
        "    import os as _os\n"
        "    from builtins import print as _builtin_print\n"
        "    input_files = list(inputs.get('files') or [])\n"
        "    input_dir = context.get('input_dir') or 'inputs'\n"
        "    _askai_output_dir = context.get('output_dir') or 'out'\n"
        "    _os.makedirs(_askai_output_dir, exist_ok=True)\n"
        "    _os.chdir(_askai_output_dir)\n"
        "    output_dir = _askai_output_dir\n"
        "    _stdout = _io.StringIO()\n"
        "    def print(*args, **kwargs):\n"
        "        kwargs.pop('file', None)\n"
        "        _builtin_print(*args, file=_stdout, **kwargs)\n"
        f"{indented}\n"
        "    _lines = _stdout.getvalue().splitlines()\n"
        "    _artifacts = []\n"
        "    for _root, _dirs, _files in _os.walk(_askai_output_dir):\n"
        "        for _name in _files:\n"
        "            _artifacts.append({'path': _os.path.join(_root, _name), 'filename': _name})\n"
        "    return {'data': {'stdout': _lines}, 'logs': _lines, 'artifacts': _artifacts}\n"
    )


__all__ = ["compile_script_plugin"]
