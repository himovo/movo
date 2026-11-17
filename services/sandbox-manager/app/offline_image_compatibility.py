"""Check package cache compatibility without requiring identical image bytes."""

from __future__ import annotations

import json
import platform
from uuid import uuid4

from .docker_engine import DockerEngine, merged_docker_logs


_PROBE = (
    "import json,os,platform,subprocess,sys; "
    "release={}; "
    "[release.update([line.split('=',1)]) for line in open('/etc/os-release') "
    "if line.startswith(('ID=','VERSION_ID='))]; "
    "print(json.dumps({'os':os.uname().sysname.lower(),"
    "'arch':platform.machine(),'distribution':release.get('ID','').strip().strip('\\\"'),"
    "'distributionMajor':release.get('VERSION_ID','').strip().strip('\\\"').split('.')[0],"
    "'libc':list(platform.libc_ver()),"
    "'python':list(sys.version_info[:2])}))"
)


def _probe(engine: DockerEngine, image: str, kind: str) -> dict:
    command = (["python", "-c", _PROBE] if kind == "script" else [
        "node", "-e",
        "const fs=require('fs');const p=require('./package.json');"
        "const r=fs.readFileSync('/etc/os-release','utf8');"
        "const get=k=>(r.match(new RegExp('^'+k+'=(.*)$','m'))||[])[1]?.replace(/\"/g,'')||'';"
        "console.log(JSON.stringify({os:process.platform,arch:process.arch,"
        "distribution:get('ID'),distributionMajor:get('VERSION_ID').split('.')[0],"
        "nodeMajor:process.versions.node.split('.')[0],dsh:p.dependencies?.['@deepseek-ai/dsh']||''}))",
    ])
    name = f"movo-offline-probe-{uuid4().hex}"
    container = engine.create(name, {
        "Image": image, "Entrypoint": command[:1], "Cmd": command[1:],
        "HostConfig": {"NetworkMode": "none", "CapDrop": ["ALL"],
                       "SecurityOpt": ["no-new-privileges:true"], "ReadonlyRootfs": True},
    })
    try:
        engine.start(container)
        if engine.wait(container, 30) != 0:
            raise ValueError(f"Cannot inspect {kind} package environment")
        return json.loads(merged_docker_logs(engine.logs(container)).decode().strip())
    finally:
        engine.remove(container)


def fingerprint(engine: DockerEngine, image: str, kind: str) -> dict:
    if not image or not engine.image_id(image):
        raise ValueError(f"{kind.capitalize()} image is unavailable for package compatibility check")
    try:
        return _probe(engine, image, kind)
    except (OSError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot inspect {kind} package environment") from exc


def verify(engine: DockerEngine, manifest: dict, *, script: bool, runtime: bool, apt: bool) -> None:
    checks = (("script", script, "baseImageId", "baseImageEnvironment", "MOVO_SANDBOX_SCRIPT_IMAGE"),
              ("runtime", runtime, "runtimeImageId", "runtimeImageEnvironment", "MOVO_SANDBOX_RUNTIME_IMAGE"))
    import os
    for kind, needed, image_key, environment_key, setting in checks:
        if not needed:
            continue
        target_image = os.environ.get(setting, "")
        if not target_image:
            continue
        target_id = engine.image_id(target_image)
        if not target_id:
            raise ValueError(f"Target {kind} image is unavailable")
        source_id = manifest.get(image_key)
        if not source_id:
            raise ValueError(f"{kind.capitalize()} image identity is missing from the archive")
        if source_id == target_id:
            continue
        if kind == "script" and apt:
            raise ValueError("System packages require the same sandbox base image")
        source = manifest.get(environment_key)
        if not source:
            # Version 1 archives have no environment metadata. Their source image
            # must be present locally so that both environments can be inspected.
            source = fingerprint(engine, source_id, kind)
        target = fingerprint(engine, target_image, kind)
        if source != target:
            raise ValueError(f"{kind.capitalize()} package environment is incompatible with this host")
