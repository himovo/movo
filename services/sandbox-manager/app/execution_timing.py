"""Phase timings for Docker preparation and execution, without command contents."""
import logging
from contextlib import contextmanager
from time import monotonic


@contextmanager
def execution_phase(phase: str, task_id: str):
    started = monotonic()
    outcome = 'failed'
    try:
        yield
        outcome = 'completed'
    finally:
        logging.getLogger('uvicorn.error').info(
            'Sandbox task=%s phase=%s outcome=%s duration_ms=%d',
            task_id, phase, outcome, int((monotonic() - started) * 1000),
        )
