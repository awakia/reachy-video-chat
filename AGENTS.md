# AGENTS.md — AI-Driven Development Guidelines

## Language Policy

**All documentation and code MUST be written in English.** This includes:

- Source code: variable names, function names, class names, comments
- Documentation: README, AGENTS.md, docstrings, inline comments
- Commit messages
- Test descriptions and assertions
- Configuration keys and descriptions

The only exception is user-facing content in profile instruction files (e.g., `profiles/*/instructions.txt`) where the target language matches the intended audience.

## Commit Strategy

### Conventional Commits

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

- `chore:` — project scaffolding, config changes, dependency updates
- `feat:` — new functionality
- `fix:` — bug fixes
- `refactor:` — code restructuring without behavior change
- `test:` — test-only changes
- `docs:` — documentation-only changes

### One Concern Per Commit

Each commit should represent a single, coherent unit of work. Structure implementation as a series of small, focused commits that build on each other. Each commit should:

- Leave the project in a working state (all tests pass)
- Be independently understandable from its diff
- Have a clear, descriptive message explaining *what* and *why*

### Verify Before Committing

Run the full test suite before every commit:

```bash
pytest tests/
ruff check src/
```

Never commit code that breaks existing tests.

## Testing Philosophy

### Test-Driven Verification

Every feature commit must include corresponding tests. Tests should:

- Run without hardware, network, or API keys
- Use mocks for external dependencies (robot SDK, Gemini API, file system)
- Cover both happy paths and error cases
- Be fast (entire suite should complete in seconds)

### Mock Boundaries, Not Internals

Mock at external boundaries:

- Robot SDK calls (`reachy_mini.ReachyMini`)
- API calls (`google.genai`)
- File system operations (use `tmp_path`, `monkeypatch`)
- Time-dependent behavior (pass explicit `current_time` parameters)

Do not mock internal classes or pure logic — test those directly.

### Test File Organization

- One test file per source module: `src/.../foo.py` → `tests/test_foo.py`
- Use `pytest` with `pytest-asyncio` for async code
- Group related tests in classes (e.g., `TestSilenceDetector`)

## Dependency Management

### Optional Dependencies for Heavy Packages

Platform-specific or large native packages must be optional:

```toml
[project.optional-dependencies]
robot = ["reachy-mini>=0.1.0", "sounddevice>=0.4"]
wake-openwakeword = ["openwakeword>=0.6.0"]
wake-edge-impulse = ["edge_impulse_linux>=1.0.0"]
```

Use lazy imports (`import` inside functions) so the core package works without optional deps:

```python
def load_model(self):
    try:
        import openwakeword
    except ImportError:
        raise ImportError("Install with: pip install reachy-mini-companion[wake-openwakeword]")
```

### Avoid Native Build Dependencies

Prefer pure-Python or pre-built wheel packages. For example, use `soxr` instead of `resampy` (which requires scipy/gfortran). Check that dependencies have wheels for the target platform before adding them.

## Architecture Patterns

### Pluggable Backends via Abstract Base Class

When multiple implementations exist for the same interface (e.g., wake word backends), use:

1. Abstract base class defining the interface (`BaseWakeWordDetector`)
2. Concrete implementations (`EdgeImpulseDetector`, `OpenWakeWordDetector`)
3. Factory function dispatching on config (`create_wake_detector(config)`)
4. Config field selecting the backend (`wake.backend: "edge_impulse"`)

### Async-First with `asyncio.to_thread()`

All blocking SDK calls must be wrapped in `asyncio.to_thread()` to avoid blocking the event loop:

```python
async def express(self, action: str, intensity: float = 1.0):
    for step in EXPRESSIONS[action]:
        await asyncio.to_thread(
            self.robot.goto_target, head=pose, duration=step["duration"]
        )
```

### Simulate Mode

All hardware-dependent components must support a simulate mode where `robot=None`. In simulate mode, log the action instead of executing it:

```python
if self.robot is not None:
    await asyncio.to_thread(self.robot.goto_target, ...)
else:
    logger.info(f"[Simulate] expression: {action}")
```

This ensures the full application can run, be tested, and be developed without hardware.

### State Machine Driven Flow

Application lifecycle is managed by a pure-logic state machine. The state machine:

- Contains no I/O or side effects
- Is fully testable with simple `send_event()` calls
- Drives the main loop via state-based dispatch

### Configuration Layering

Config is loaded in layers with increasing priority:

1. `config/default.yaml` — sensible defaults (committed)
2. `config/config.yaml` — user overrides (gitignored)
3. `.env` file — secrets (gitignored)
4. Environment variables — runtime overrides
5. CLI arguments — highest priority

Use Pydantic models for typed, validated configuration.

## Code Quality

### Target Python Version

Target Python 3.10+ (`requires-python = ">=3.10"`). Do not use syntax or features from later versions (e.g., `except*` requires 3.11+, `type` statements require 3.12+).

### Linting

Use `ruff` for linting and formatting. Fix all lint errors before committing. Key rules:

- Remove unused imports
- No bare `except:` clauses
- Consistent string quoting

### Error Handling

- Log warnings for non-fatal issues (missing sound files, unavailable hardware)
- Use specific exception types, not bare `except:`
- Provide actionable error messages that guide the user toward resolution

### Minimal Boilerplate

- Use `from __future__ import annotations` for modern type hint syntax
- Keep `__init__.py` files minimal (empty or just exports)
- Prefer dataclasses/Pydantic models over raw dicts for structured data

## Project Summary

This project (`reachy-mini-companion`) is a wake-word triggered AI companion for the Reachy Mini robot. Key components:

| Component | Location | Purpose |
|-----------|----------|---------|
| Config | `src/.../config.py` | Pydantic-based config with YAML + .env |
| State Machine | `src/.../state_machine.py` | SETUP → SLEEPING → WAKING → ACTIVE → COOLDOWN |
| Wake Word | `src/.../wake/` | Pluggable: Edge Impulse (default) or openWakeWord |
| Gemini Session | `src/.../conversation/` | Bidirectional audio streaming via Gemini Live API |
| Robot Control | `src/.../robot/` | Movement, expressions, audio I/O, sound effects |
| Tools | `src/.../tools/` | Function calling: expressions + look directions |
| Cost Tracking | `src/.../cost/` | SQLite-based session cost estimation + budget |
| Web UI | `src/.../web/` | Gradio setup wizard for API key entry |
| Profiles | `profiles/` | System prompts + tool configs per persona |
