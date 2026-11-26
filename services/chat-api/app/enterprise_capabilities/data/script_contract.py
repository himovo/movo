"""Compile DSH-friendly Python into the mature sandbox plugin contract."""

from __future__ import annotations

import ast


def _indent_script_body(source: str, tree: ast.Module) -> str:
    literal_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr) or (
            isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes))
        ):
            # The first line starts in Python code. Prefixing later lines
            # can change the literal value, including at the closing quotes.
            literal_lines.update(range(node.lineno + 1, node.end_lineno + 1))
    # Match the physical newline rules used by the Python parser.
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(
        line if line_number in literal_lines or not line.strip() else "    " + line
        for line_number, line in enumerate(lines, start=1)
    )


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
    indented = _indent_script_body(source, tree)
    return (
        "def run(inputs, context):\n"
        "    import io as _io\n"
        "    import os as _os\n"
        "    from builtins import print as _builtin_print\n"
        "    input_files = list(inputs.get('files') or [])\n"
        "    input_dir = context.get('input_dir') or 'inputs'\n"
        "    work_dir = context.get('work_dir') or '.'\n"
        "    home_dir = context.get('home_dir') or ''\n"
        "    conversation_dir = context.get('conversation_dir') or ''\n"
        "    _askai_output_dir = context.get('output_dir') or 'out'\n"
        "    _os.makedirs(_askai_output_dir, exist_ok=True)\n"
        "    import sys as _sys\n"
        "    _cache_dir = _os.path.join(work_dir, '.cache', 'python')\n"
        "    _os.makedirs(_cache_dir, exist_ok=True)\n"
        "    _sys.pycache_prefix = _cache_dir\n"
        "    _os.environ['PYTHONPYCACHEPREFIX'] = _cache_dir\n"
        "    _os.chdir(_askai_output_dir)\n"
        "    output_dir = _askai_output_dir\n"
        "    skill_dir = context.get('skill_dir') or ''\n"
        "    _stdout = _io.StringIO()\n"
        "    def print(*args, **kwargs):\n"
        "        kwargs.pop('file', None)\n"
        "        _builtin_print(*args, file=_stdout, **kwargs)\n"
        f"{indented}\n"
        "    _lines = _stdout.getvalue().splitlines()\n"
        "    _artifacts = []\n"
        "    for _root, _dirs, _files in _os.walk(_askai_output_dir):\n"
        "        _dirs[:] = [_dir for _dir in _dirs if _dir != '__pycache__']\n"
        "        for _name in _files:\n"
        "            _artifacts.append({'path': _os.path.relpath(_os.path.join(_root, _name), _askai_output_dir), 'filename': _name})\n"
        "    return {'data': {'stdout': _lines}, 'logs': _lines, 'artifacts': _artifacts}\n"
    )


__all__ = ["compile_script_plugin"]
