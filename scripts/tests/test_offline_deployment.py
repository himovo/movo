"""Offline bundle and upgrade safety tests without a Docker daemon."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy/offline"))
import common
import prepare
import install
import upgrade


def test_env_merge_preserves_customer_settings_and_removes_duplicate_release_keys():
    original = 'MOVO_PORT=3002\nSECRET="keep-me"\nMOVO_VERSION=old\nMOVO_VERSION=older\n'
    result = common.merge_env(original, {"MOVO_VERSION": "new", "MOVO_OFFLINE_ONLY": "1"})
    assert 'SECRET="keep-me"' in result and 'MOVO_PORT=3002' in result
    assert result.count('MOVO_VERSION=') == 1
    assert 'MOVO_VERSION=new' in result


def test_safe_paths_reject_traversal_and_symlinks(tmp_path):
    with pytest.raises(ValueError):
        common.safe_path(tmp_path, '../outside')
    (tmp_path / 'escape').symlink_to('/tmp')
    with pytest.raises(ValueError):
        common.safe_path(tmp_path, 'escape/file')


def test_bundle_rejects_corruption_before_docker_access(tmp_path, monkeypatch):
    manifest = {"schema": 1, "architecture": "arm64", "release": "r1", "images": [],
                "files": {"images.tar": "wrong"}}
    (tmp_path / 'images.tar').write_bytes(b'corrupt')
    (tmp_path / 'offline-manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(install, 'run', lambda *a, **k: pytest.fail('Docker accessed before checksum verification'))
    with pytest.raises(ValueError, match='checksum mismatch'):
        install.install(tmp_path, tmp_path / 'target', tmp_path / 'backups')


def test_platform_mismatch_stops_before_import(tmp_path, monkeypatch):
    monkeypatch.setattr(install, 'verify_bundle', lambda _: {'architecture': 'arm64'})
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return json.dumps({'Architecture': 'x86_64', 'OSType': 'linux', 'ServerVersion': '28.0.1'})
    monkeypatch.setattr(install, 'run', run)
    with pytest.raises(ValueError, match='platform'):
        install.install(tmp_path, tmp_path / 'target', tmp_path / 'backups')
    assert len(calls) == 1 and 'info' in calls[0]


def test_upgrade_preserves_identity_and_volume_names(tmp_path, monkeypatch):
    source, target = tmp_path / 'source', tmp_path / 'existing'
    source.mkdir(); target.mkdir()
    (source / 'release.env').write_text('MOVO_VERSION=new\nCOMPOSE_PROJECT_NAME=default\nMOVO_PORT=3000\n')
    (source / 'offline-compose.json').write_text(json.dumps({'services': {
        'bootstrap': {'image': 'offline:alpine'}, 'sandbox-script': {'image': 'offline:script'}}}))
    (target / '.env').write_text('MOVO_VERSION=old\nMOVO_PORT=3002\nCUSTOM_SECRET=secret\n')
    (target / 'docker-compose.yml').write_text('old')
    old = {'name': 'customer-project', 'volumes': {'mongo-data': {'name': 'original_mongo'}}, 'services': {}}
    monkeypatch.setattr(upgrade, 'config', lambda *a, **k: old)
    env, volumes, _ = upgrade.deployment_env(source, target)
    assert 'MOVO_PORT=3002' in env and 'CUSTOM_SECRET=secret' in env
    assert 'COMPOSE_PROJECT_NAME=customer-project' in env
    assert volumes['mongo-data']['name'] == 'original_mongo'
    assert 'MOVO_SANDBOX_SCRIPT_IMAGE=offline:script' in env


def test_other_deployment_project_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(upgrade, 'run', lambda args, **kwargs:
        'container\n' if 'ps' in args else json.dumps([{'Config': {'Labels': {
            'com.docker.compose.project.working_dir': '/different/deployment'}}}]))
    with pytest.raises(ValueError, match='different'):
        upgrade.check_identity(tmp_path, {'name': 'customer'})


def test_prepare_does_not_copy_credentials_or_source(tmp_path):
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir(); target.mkdir()
    for name in ('movo', 'docker-compose.yml', 'release.json', 'INSTALL.txt',
                 'prepare-offline.sh', 'install-offline.sh', 'release.env'):
        (source / name).write_text('release')
    (source / '.env').write_text('CUSTOM_SECRET=private')
    (source / 'source.py').write_text('private source')
    for name in ('cli', 'offline', 'docker'):
        (source / 'deploy' / name).mkdir(parents=True)
    (source / 'deploy/docker/nginx.conf').write_text('release')
    prepare.copy_payload(source, target)
    assert (target / '.env').read_text() == 'release'
    assert not (target / 'source.py').exists()


def test_backup_refuses_writable_bind_before_stopping(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(upgrade, 'run', lambda args, **k: calls.append(args) or '')
    (tmp_path / 'deployment').mkdir()
    resolved = {'name': 'customer', 'services': {'custom': {'volumes': [
        {'type': 'bind', 'source': '/customer-data', 'read_only': False}]}}, 'volumes': {}}
    with pytest.raises(ValueError, match='Writable bind'):
        upgrade.backup(tmp_path / 'deployment', resolved, 'local:alpine', tmp_path / 'backups')
    assert not any('stop' in args for args in calls)


def test_backup_failure_restarts_original_services_without_migration(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(upgrade, 'compose', lambda: ['docker', 'compose'])
    def run(args, **kwargs):
        calls.append(args)
        if 'du' in args:
            return '1 /source\n'
        if 'tar' in args:
            raise RuntimeError('disk write failed')
        return ''
    monkeypatch.setattr(upgrade, 'run', run)
    target = tmp_path / 'deployment'; target.mkdir()
    with pytest.raises(RuntimeError, match='disk write failed'):
        upgrade.backup(target, {'name': 'customer', 'services': {}, 'volumes': {'data': {'name': 'original'}}},
                       'local:alpine', tmp_path / 'backups')
    assert calls[-1] == ['docker', 'compose', 'start']
    assert not any('app.migrations' in args for args in calls)
