"""Configuration system with YAML defaults + user overrides + .env secrets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"
USER_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
ENV_PATH = PROJECT_ROOT / ".env"


class SecretSettings(BaseSettings):
    """Loads secrets from .env file and environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: str = ""


# --- Nested config sections ---


class ReachyConfig(BaseModel):
    connection_mode: str = "auto"  # "auto", "localhost", or "network"
    simulate: bool = False


class WakeConfig(BaseModel):
    backend: str = "edge_impulse"  # "edge_impulse" or "openwakeword"
    model: str = "hey_reachy"  # builtin model name
    custom_model_path: str | None = None  # path to custom .onnx/.tflite/.eim
    threshold: float = 0.7
    refractory_sec: float = 3.0


class GeminiConfig(BaseModel):
    model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    voice: str = "Aoede"
    input_sample_rate: int = 16000
    output_sample_rate: int = 24000


class SessionConfig(BaseModel):
    max_duration_sec: int = 300
    silence_timeout_sec: int = 15
    cooldown_sec: int = 5
    silence_rms_threshold: int = 200


class PromptConfig(BaseModel):
    default_profile: str = "default"
    profiles_dir: str = "profiles"


class RobotConfig(BaseModel):
    wake_up_duration: float = 1.0
    sleep_duration: float = 1.5
    expression_speed: float = 1.0


class PricingConfig(BaseModel):
    input_audio_per_million: float = 0.70
    output_audio_per_million: float = 7.00
    input_text_per_million: float = 0.15
    output_text_per_million: float = 0.60


class CostConfig(BaseModel):
    db_path: str = "data/cost.db"
    daily_budget_usd: float = 1.00
    pricing: PricingConfig = Field(default_factory=PricingConfig)


class WebUIConfig(BaseModel):
    enabled: bool = True
    port: int = 7860
    host: str = "0.0.0.0"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "logs/companion.log"


class AppConfig(BaseModel):
    """Full application configuration."""

    reachy: ReachyConfig = Field(default_factory=ReachyConfig)
    wake: WakeConfig = Field(default_factory=WakeConfig)
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    robot: RobotConfig = Field(default_factory=RobotConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    web_ui: WebUIConfig = Field(default_factory=WebUIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Secrets (populated from .env / environment)
    google_api_key: str = ""

    @property
    def has_api_key(self) -> bool:
        return bool(self.google_api_key)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base dict."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning empty dict if missing."""
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data or {}


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load config by merging: defaults -> user config.yaml -> .env/env vars.

    Args:
        config_path: Optional path to a user config YAML override file.
    """
    # 1. Load default config
    data = _load_yaml(DEFAULT_CONFIG_PATH)

    # 2. Merge user config override
    user_path = Path(config_path) if config_path else USER_CONFIG_PATH
    user_data = _load_yaml(user_path)
    if user_data:
        data = _deep_merge(data, user_data)

    # 3. Load secrets from .env / environment
    secrets = SecretSettings()

    # 4. Inject secrets
    if secrets.google_api_key:
        data["google_api_key"] = secrets.google_api_key

    return AppConfig(**data)


def save_api_key(key: str) -> None:
    """Write API key to .env file with restricted permissions."""
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Read existing .env content (if any), replace or append key
    lines: list[str] = []
    found = False
    if ENV_PATH.exists():
        with open(ENV_PATH) as f:
            for line in f:
                if line.startswith("GOOGLE_API_KEY="):
                    lines.append(f"GOOGLE_API_KEY={key}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"GOOGLE_API_KEY={key}\n")

    with open(ENV_PATH, "w") as f:
        f.writelines(lines)
    os.chmod(ENV_PATH, 0o600)


def save_config(updates: dict[str, Any]) -> None:
    """Save config updates to user config.yaml."""
    USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_yaml(USER_CONFIG_PATH)
    merged = _deep_merge(existing, updates)
    with open(USER_CONFIG_PATH, "w") as f:
        yaml.dump(merged, f, default_flow_style=False)
