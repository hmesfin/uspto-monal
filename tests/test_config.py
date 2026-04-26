import os
import pytest
from pathlib import Path
from uspto.config import Config, load_config, ConfigError


def test_load_config_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("USPTO_API_KEY", "abc123")
    monkeypatch.setenv("USPTO_DB_PATH", str(tmp_path / "x.db"))
    cfg = load_config()
    assert cfg.api_key == "abc123"
    assert cfg.db_path == (tmp_path / "x.db").resolve()


def test_load_config_missing_api_key_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("uspto.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("USPTO_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="USPTO_API_KEY"):
        load_config()


def test_load_config_default_db_path(monkeypatch):
    monkeypatch.setattr("uspto.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("USPTO_API_KEY", "abc")
    monkeypatch.delenv("USPTO_DB_PATH", raising=False)
    cfg = load_config()
    assert cfg.db_path.is_absolute()
    assert str(cfg.db_path).endswith("uspto/trademarks.db")


def test_db_path_expands_user(monkeypatch):
    monkeypatch.setenv("USPTO_API_KEY", "abc")
    monkeypatch.setenv("USPTO_DB_PATH", "~/foo.db")
    cfg = load_config()
    assert "~" not in str(cfg.db_path)
    assert cfg.db_path.is_absolute()
