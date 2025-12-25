from pathlib import Path

from app.services import provider_status


def test_resolve_openai_key_prefers_env(monkeypatch, tmp_path: Path):
    secrets_path = tmp_path / "secrets.toml"
    secrets_path.write_text('OPENAI_API_KEY = "file-value"\n', encoding="utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "env-value")

    value, source = provider_status.resolve_api_key(
        "OPENAI_API_KEY",
        secret_paths=[secrets_path],
    )

    assert value == "env-value"
    assert source == "env"
