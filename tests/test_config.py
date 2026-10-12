"""Regression test for a real bug found while saving a live CJ API key:
load_settings() used os.environ.get(KEY, default) directly for fields with
a real non-empty default (CJ_API_BASE_URL, SHOPIFY_API_VERSION, etc.) - but
os.environ.get only falls back to its default when the key is entirely
ABSENT, not when .env defines it blank (e.g. "CJ_API_BASE_URL="), which
.env.example's own template does. A blank .env value silently beat the
Python default and produced an unusable empty base URL.
"""
from __future__ import annotations

from src.config import load_settings


def test_a_blank_cj_api_base_url_in_env_falls_back_to_the_real_default(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("CJ_API_BASE_URL=\nCJ_API_KEY=some-key\n")
    for key in ("CJ_API_BASE_URL", "CJ_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    settings = load_settings(env_file)

    assert settings.cj_api_base_url == "https://developers.cjdropshipping.com/api2.0/v1"
    assert settings.cj_api_key == "some-key"  # a real blank-looking secret still has no fallback


def test_a_blank_shopify_api_version_falls_back_to_the_default(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SHOPIFY_API_VERSION=\n")
    monkeypatch.delenv("SHOPIFY_API_VERSION", raising=False)

    settings = load_settings(env_file)

    assert settings.shopify_api_version == "2024-07"


def test_an_explicit_cj_api_base_url_in_env_is_still_respected(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("CJ_API_BASE_URL=https://example.com/custom\n")
    monkeypatch.delenv("CJ_API_BASE_URL", raising=False)

    settings = load_settings(env_file)

    assert settings.cj_api_base_url == "https://example.com/custom"
