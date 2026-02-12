# Reachy Mini AI Companion

"Hey Reachy" wake-word triggered AI companion for Reachy Mini (Wireless).

## Prerequisites

- Python 3.10+
- Reachy Mini robot (or `--simulate` mode for development)
- Google Gemini API key ([get one here](https://aistudio.google.com/apikey))

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```bash
# First run will launch setup wizard for API key
reachy-mini-companion

# With simulation mode (no robot needed)
reachy-mini-companion --simulate

# Custom config
reachy-mini-companion --config config/config.yaml
```

## Development

```bash
pytest tests/
ruff check src/
```
