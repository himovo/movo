from __future__ import annotations

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from zipfile import ZipFile

from app.execution_isolation.runner_source import runner_source


def _run(work: Path, code: str, call: str, *, skill_dir: str = "", allow_network: bool = False) -> subprocess.CompletedProcess[str]:
    folder = work / "calls" / call
    folder.mkdir(parents=True)
    (folder / "runner.py").write_text(runner_source(container_isolated=True))
    (folder / "plugin.py").write_text(code)
    (folder / "stdin.json").write_text(json.dumps({
        "inputs": {}, "context": {"work_dir": str(work), "skill_dir": skill_dir, "allow_network": allow_network},
    }))
    return subprocess.run([sys.executable, "-I", str(folder / "runner.py"),
                           str(folder / "plugin.py"), str(folder / "stdin.json")],
                          text=True, capture_output=True, check=False)


def test_isolated_runner_reuses_workspace_and_accepts_one_argument(tmp_path: Path) -> None:
    first = _run(tmp_path, "def run(inputs):\n    open('intermediate.log', 'w').write('kept')\n    return {}\n", "a")
    second = _run(tmp_path, "def run():\n    return {'value': open('intermediate.log').read()}\n", "b")
    assert first.returncode == 0
    assert second.returncode == 0
    assert json.loads(second.stdout)["value"] == "kept"


def test_isolated_runner_loads_task_local_dependency_on_later_call(tmp_path: Path) -> None:
    wheel = tmp_path / "probe_package-1.0-py3-none-any.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("probe_package.py", "value = 42\n")
        archive.writestr("probe_package-1.0.dist-info/METADATA", "Metadata-Version: 2.1\nName: probe-package\nVersion: 1.0\n")
        archive.writestr("probe_package-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        archive.writestr("probe_package-1.0.dist-info/RECORD", "")
    first = _run(tmp_path, "def run(inputs, context):\n    import subprocess, sys\n    from pathlib import Path\n    target = Path(context['work_dir']) / '.dependencies/python'\n    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--target', str(target), str(Path(context['work_dir']) / 'probe_package-1.0-py3-none-any.whl')], check=True, capture_output=True)\n    return {}\n", "a")
    second = _run(tmp_path, "def run():\n    import probe_package\n    return {'value': probe_package.value}\n", "b")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0
    assert json.loads(second.stdout)["value"] == 42


def test_isolated_runner_downloads_csv_and_returns_monthly_totals(tmp_path: Path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"date,sales\n2026-01-03,10\n2026-01-20,5\n2026-02-01,7\n"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        code = """def run(inputs, context):
    import csv
    import subprocess
    from collections import defaultdict
    from pathlib import Path
    target = Path(context['work_dir']) / 'sales.csv'
    subprocess.run(['curl', '--fail', '--silent', '--show-error', '--noproxy', '*',
                    '-o', str(target), 'http://127.0.0.1:%d/sales.csv'], check=True)
    totals = defaultdict(int)
    with target.open(newline='') as stream:
        for row in csv.DictReader(stream):
            totals[row['date'][:7]] += int(row['sales'])
    return {'months': dict(totals)}
""" % server.server_port
        result = _run(tmp_path, code, "csv", allow_network=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["months"] == {"2026-01": 15, "2026-02": 7}
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_isolated_runner_reads_selected_skill_files(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("name: sample-skill")
    result = _run(tmp_path, "def run(inputs, context):\n    from pathlib import Path\n    return {'skill': Path(context['skill_dir'], 'SKILL.md').read_text()}\n", "skill", skill_dir=str(skill_dir))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["skill"] == "name: sample-skill"
