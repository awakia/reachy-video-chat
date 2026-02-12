"""Tests for setup wizard validation logic."""

from unittest.mock import MagicMock, patch

from reachy_mini_companion.web.setup_wizard import validate_api_key


def test_validate_empty_key():
    success, msg = validate_api_key("")
    assert success is False
    assert "enter" in msg.lower()


def test_validate_whitespace_key():
    success, msg = validate_api_key("   ")
    assert success is False


@patch("reachy_mini_companion.web.setup_wizard.genai", create=True)
def test_validate_valid_key(mock_genai_module):
    """Valid key should return success."""
    with patch("google.genai.Client") as MockClient:
        mock_client = MagicMock()
        mock_client.models.list.return_value = [MagicMock(), MagicMock()]
        MockClient.return_value = mock_client

        success, msg = validate_api_key("valid-key-123")
        assert success is True
        assert "valid" in msg.lower() or "Valid" in msg


@patch("google.genai.Client")
def test_validate_invalid_key(MockClient):
    """Invalid key should return failure."""
    MockClient.side_effect = Exception("Invalid API key")
    success, msg = validate_api_key("bad-key")
    assert success is False
    assert "invalid" in msg.lower() or "Invalid" in msg
