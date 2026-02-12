# AGENTS.md

## Rules

- All documentation, code, and commit messages in English
  - Exception: `profiles/*/instructions.txt` may use target language
- Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`)
- One concern per commit; every commit must pass `pytest tests/` and `ruff check src/`
- Every feature includes tests that run without hardware, network, or API keys
- Mock at external boundaries (robot SDK, Gemini API, FS), not internals
- Python 3.10+ — no syntax from later versions
- Heavy/platform-specific deps are optional; use lazy imports with helpful ImportError messages
- Prefer pre-built wheels over packages requiring native compilation
- Blocking SDK calls wrapped in `asyncio.to_thread()`
- All hardware components support simulate mode (`robot=None` → log instead)
- Config priority: `config/default.yaml` < `config/config.yaml` < `.env` < env vars < CLI args
- Pluggable backends: ABC + concrete implementations + factory function + config selector

## Project Structure

`reachy-mini-companion`: wake-word triggered AI companion for Reachy Mini.

| Component | Location |
|-----------|----------|
| Config | `src/.../config.py` — Pydantic + YAML + .env |
| State Machine | `src/.../state_machine.py` — SETUP→SLEEPING→WAKING→ACTIVE→COOLDOWN |
| Wake Word | `src/.../wake/` — Edge Impulse (default) / openWakeWord |
| Gemini Session | `src/.../conversation/` — Bidirectional audio via Gemini Live API |
| Robot Control | `src/.../robot/` — Movement, expressions, audio, sounds |
| Tools | `src/.../tools/` — Function calling for expressions + look directions |
| Cost Tracking | `src/.../cost/` — SQLite session cost + budget |
| Web UI | `src/.../web/` — Gradio setup wizard |
| Profiles | `profiles/` — System prompts + tool configs per persona |
