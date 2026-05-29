import sys, os, pytest
from unittest.mock import patch, mock_open, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from actions.whatsapp_web import _normalize_phone, _get_api_key


class TestNormalizePhone:
    def test_br_number_with_country_code(self):
        assert _normalize_phone("+5511999999999") == "5511999999999"

    def test_br_number_without_prefix(self):
        result = _normalize_phone("11999999999")
        assert result == "5511999999999"

    def test_br_number_11_digits_no_prefix(self):
        result = _normalize_phone("11987654321")
        assert result == "5511987654321"

    def test_br_number_10_digits_no_prefix(self):
        result = _normalize_phone("1198765432")
        assert result == "551198765432"

    def test_empty_string(self):
        assert _normalize_phone("") == ""

    def test_none_value(self):
        assert _normalize_phone(None) == ""

    def test_only_digits_extracted(self):
        result = _normalize_phone("+55 (11) 99999-9999")
        assert result == "5511999999999"

    def test_us_number(self):
        assert _normalize_phone("+12125551234") == "12125551234"

    def test_with_55_prefix(self):
        result = _normalize_phone("5511987654321")
        assert result == "5511987654321"

    def test_known_country_code_portugal(self):
        assert _normalize_phone("+351912345678") == "351912345678"

    def test_known_country_code_uk(self):
        assert _normalize_phone("+447911123456") == "447911123456"

    def test_non_digit_returns_empty(self):
        assert _normalize_phone("abc") == ""


class TestGetApiKey:
    @patch("builtins.open", new_callable=mock_open, read_data='{"gemini_api_key": "test_key_123"}')
    def test_reads_api_key(self, mock_file):
        key = _get_api_key()
        assert key == "test_key_123"

    @patch("builtins.open", new_callable=mock_open, read_data='{}')
    def test_missing_key_returns_empty(self, mock_file):
        key = _get_api_key()
        assert key == ""

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_file_not_found_returns_empty(self, mock_file):
        key = _get_api_key()
        assert key == ""
