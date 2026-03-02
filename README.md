---
title: Reachy Mini AI Companion
emoji: "\U0001F916"
colorFrom: blue
colorTo: purple
sdk: static
pinned: false
short_description: Hey Reachy wake-word AI companion powered by Gemini
tags:
  - reachy_mini
  - reachy_mini_python_app
---

# Reachy Mini AI Companion

"Hey Reachy" wake-word triggered conversational AI companion for [Reachy Mini](https://www.pollen-robotics.com/reachy-mini/).

Uses **Gemini 2.5 Flash** native audio for real-time voice conversations with robot expressions, gestures, and automatic session reconnection.

## Features

- **Voice conversations** — bidirectional audio via Gemini Live API (native audio model)
- **Wake word detection** — "Hey Reachy" using Edge Impulse (auto-downloads from HuggingFace)
- **Robot expressions** — nods, shakes, looks, and gestures during conversation via function calling
- **Session reconnection** — automatic reconnect with context preservation on session timeouts
- **Cost tracking** — per-session cost estimation with daily budget limits (SQLite)
- **Personality profiles** — customizable system prompts and tool sets per persona
- **Simulate mode** — web dashboard with WebRTC audio for development without robot hardware

## Prerequisites

- Python 3.10+
- Google Gemini API key ([get one here](https://aistudio.google.com/apikey))
- Reachy Mini robot (or use `--simulate` for development)

## Quick Start

### Development (no robot)

```bash
# Install
git clone https://github.com/awakia/reachy-video-chat.git
cd reachy-video-chat
pip install -e ".[dev,dashboard]"

# Configure API key
mkdir -p ~/.reachy-mini-companion
cp .env.example ~/.reachy-mini-companion/.env
# Edit ~/.reachy-mini-companion/.env with your API key

# Run in simulate mode (opens web dashboard at http://localhost:7860)
reachy-mini-companion --simulate
```

### Deploy to Reachy Mini

**From the Dashboard** — find "reachy_video_chat" in the Reachy Mini dashboard's app store and click Install.

**Manual install:**

```bash
ssh pollen@reachy-mini.local  # password: root

# One-line install (clones repo, installs into apps venv)
curl -fsSL https://raw.githubusercontent.com/awakia/reachy-video-chat/main/deploy/install.sh | bash
```

The installer will:
1. Clone the repository to `~/reachy-mini-companion`
2. Install into the shared apps venv (`/venvs/apps_venv/`)
3. Prompt for your Gemini API key (saved to `~/.reachy-mini-companion/.env`)

After installation, the app appears in the Reachy Mini dashboard. If not, restart the daemon:
```bash
sudo systemctl restart reachy-mini-daemon
```

## Configuration

Configuration is layered with the following priority (highest wins):

| Layer | Location | Purpose |
|-------|----------|---------|
| CLI args | `--simulate`, `--connection-mode`, etc. | Runtime overrides |
| Environment / `.env` | `~/.reachy-mini-companion/.env` | Secrets (API key) |
| User config | `~/.reachy-mini-companion/config.yaml` | User customization |
| Defaults | Bundled `data/default.yaml` | Sensible defaults |

### Key settings

```yaml
# ~/.reachy-mini-companion/config.yaml
reachy:
  connection_mode: "auto"  # "auto", "localhost", or "network"

gemini:
  voice: "Aoede"  # Gemini voice preset

session:
  max_duration_sec: 300    # Max conversation length
  silence_timeout_sec: 15  # End session after silence

cost:
  daily_budget_usd: 1.00   # Daily spending limit

prompt:
  default_profile: "default"  # Personality profile to use
```

## Personality Profiles

Profiles live in `data/profiles/<name>/` and contain:
- `instructions.txt` — system prompt (can be in any language)
- `tools.txt` — list of enabled function-calling tools

Built-in profiles:
- **default** — friendly, curious robot companion (Japanese)
- **kids** — child-friendly mode

To create a custom profile, add a new directory under `data/profiles/` or set `prompt.profiles_dir` to a custom path in your config.

## Architecture

```
State Machine: SETUP -> SLEEPING -> WAKING -> ACTIVE -> COOLDOWN -> SLEEPING
                                      |                    ^
                                      v                    |
                                 [budget check]      [auto-reconnect]
                                 [API validation]    [session timeout]
```

| Component | Description |
|-----------|-------------|
| State Machine | Manages lifecycle: sleep, wake, active conversation, cooldown |
| Wake Word | Edge Impulse or openWakeWord backend (pluggable) |
| Gemini Session | Bidirectional audio streaming with auto-reconnection |
| Robot Control | Movement controller for expressions and gestures |
| Tool Dispatcher | Function calling for `robot_expression` and `robot_look_at` |
| Cost Tracker | Per-session cost estimation with SQLite persistence |
| Web Dashboard | Gradio-based UI with WebRTC audio for simulate mode |

## Development

```bash
# Run tests
pytest tests/

# Lint
ruff check src/

# Dry run (validate config without starting)
reachy-mini-companion --dry-run
```

## License

[MIT](LICENSE)
