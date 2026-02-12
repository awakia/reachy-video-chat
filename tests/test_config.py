"""Tests for configuration system."""

import os
from pathlib import Path
from unittest.mock import patch

import yaml

from reachy_mini_companion.config import (
    AppConfig,
    _deep_merge,
    load_config,
    save_api_key,
)


def test_default_config_loads():
    """Default config should load with sensible defaults."""
    config = load_config()
    assert config.reachy.connection_mode == "auto"
    assert config.gemini.voice == "Aoede"
    assert config.session.max_duration_sec == 300
    assert config.cost.pricing.input_audio_per_million == 0.70


def test_deep_merge():
    """Deep merge should recursively merge dicts."""
    base = {"a": 1, "nested": {"x": 10, "y": 20}}
    override = {"b": 2, "nested": {"y": 99}}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": 2, "nested": {"x": 10, "y": 99}}


def test_yaml_override(tmp_path):
    """User YAML config should override defaults."""
    override_file = tmp_path / "override.yaml"
    override_file.write_text(yaml.dump({"session": {"max_duration_sec": 600}}))
    config = load_config(config_path=override_file)
    assert config.session.max_duration_sec == 600
    # Other defaults preserved
    assert config.gemini.voice == "Aoede"


def test_env_var_override():
    """Environment variables should set secrets."""
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key-123"}):
        config = load_config()
    assert config.google_api_key == "test-key-123"
    assert config.has_api_key is True


def test_has_api_key_false():
    """has_api_key should be False when no key is set."""
    with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}, clear=False):
        config = load_config()
    assert config.has_api_key is False


def test_save_api_key(tmp_path, monkeypatch):
    """save_api_key should write key to .env file."""
    env_file = tmp_path / ".env"
    monkeypatch.setattr("reachy_mini_companion.config.ENV_PATH", env_file)
    save_api_key("my-secret-key")
    content = env_file.read_text()
    assert "GOOGLE_API_KEY=my-secret-key" in content
    assert oct(env_file.stat().st_mode)[-3:] == "600"


def test_save_api_key_replaces_existing(tmp_path, monkeypatch):
    """save_api_key should replace existing key."""
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_API_KEY=old-key\nOTHER_VAR=keep\n")
    monkeypatch.setattr("reachy_mini_companion.config.ENV_PATH", env_file)
    save_api_key("new-key")
    content = env_file.read_text()
    assert "GOOGLE_API_KEY=new-key" in content
    assert "OTHER_VAR=keep" in content
    assert "old-key" not in content


def test_app_config_defaults():
    """AppConfig should have correct defaults even without YAML."""
    config = AppConfig()
    assert config.reachy.simulate is False
    assert config.wake.threshold == 0.7
    assert config.wake.backend == "edge_impulse"
    assert config.web_ui.port == 7860
