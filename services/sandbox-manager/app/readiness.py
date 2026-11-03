"""Read-only readiness for resources required before offering code execution."""
import os
from urllib.parse import quote

from .docker_engine import DockerEngine


def script_readiness() -> dict:
    image = os.environ.get('MOVO_SANDBOX_SCRIPT_IMAGE', '').strip()
    if not image:
        return {'scripts': False}
    engine = DockerEngine()
    try:
        engine.request('GET', f'/images/{quote(image, safe="")}/json', timeout=0.4)
        return {'scripts': True}
    except Exception:
        return {'scripts': False}
    finally:
        engine.client.close()
