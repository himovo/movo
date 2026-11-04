from __future__ import annotations

from app.docker_engine import DockerEngine


def test_script_network_has_outbound_routing(monkeypatch) -> None:
    engine = DockerEngine.__new__(DockerEngine)
    payloads = []

    class Response:
        def json(self):
            return {"Id": "network-id"}

    def request(method, path, **kwargs):
        assert (method, path) == ("POST", "/networks/create")
        payloads.append(kwargs["json"])
        return Response()

    monkeypatch.setattr(engine, "request", request)
    assert engine.create_outbound_network("movo-task-test") == "network-id"
    assert payloads[0]["Internal"] is False
    assert engine.create_internal_network("movo-deps-test") == "network-id"
    assert payloads[1]["Internal"] is True
