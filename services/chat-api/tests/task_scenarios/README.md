# Task scenario tests

This directory contains contract-based tests for task execution. Scenarios assert
stable business contracts (capabilities, tool calls, terminal state, required
facts) instead of exact model wording or an exact node-by-node graph.

## Run

```bash
cd services/chat-api
venv/bin/python -m pytest tests/task_scenarios -q
```

## Modes

- `CallableStreamAdapter` is used by deterministic framework tests and recorded
  event replays.
- `GraphOrchestratorAdapter` calls the production `run_stream()` method without
  changing production code. Instantiate it with a configured
  `TaskGraphRuntimeOrchestrator` in integration or nightly tests.
- `FixtureToolExecutor` returns isolated fixture results and records tool calls.
  It is the test double to register at the runtime executor boundary in the next
  integration layer.

## Scenario contract

Each YAML file contains a prompt and assertions under `expect`:

- `status`: expected terminal status.
- `graph.required_capabilities`: capabilities that must exist in TaskIR or the
  task contract.
- `tools`: exact or minimum tool-call counts.
- `output.required_facts`: business facts that must appear in the answer.
- `forbidden.events`: event types that must not occur.

Do not assert exact generated text, generated node IDs, or a single rigid graph
shape unless that detail is itself a product contract.
