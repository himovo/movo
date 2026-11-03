from types import SimpleNamespace

from app import readiness


def test_missing_image_is_not_ready(monkeypatch):
    monkeypatch.delenv('MOVO_SANDBOX_SCRIPT_IMAGE', raising=False)
    assert readiness.script_readiness() == {'scripts': False}


def test_ready_requires_image_inspection_and_closes_client(monkeypatch):
    monkeypatch.setenv('MOVO_SANDBOX_SCRIPT_IMAGE', 'private.example/worker:v3')
    calls = []
    engine = SimpleNamespace(request=lambda *args, **kwargs: calls.append((args, kwargs)),
                             client=SimpleNamespace(close=lambda: calls.append('closed')))
    monkeypatch.setattr(readiness, 'DockerEngine', lambda: engine)
    assert readiness.script_readiness() == {'scripts': True}
    assert 'private.example%2Fworker%3Av3' in calls[0][0][1]
    assert calls[-1] == 'closed'


def test_missing_or_unreachable_image_is_not_ready(monkeypatch):
    monkeypatch.setenv('MOVO_SANDBOX_SCRIPT_IMAGE', 'worker:v3')
    def fail(*args, **kwargs):
        raise RuntimeError('image not found')
    monkeypatch.setattr(readiness, 'DockerEngine', lambda: SimpleNamespace(
        request=fail, client=SimpleNamespace(close=lambda: None)))
    assert readiness.script_readiness() == {'scripts': False}
