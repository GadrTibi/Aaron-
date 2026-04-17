from pathlib import Path

from app.services import provider_status


def test_provider_status_openai_priority(monkeypatch, tmp_path: Path):
    local_path = tmp_path / "local_secrets.toml"
    streamlit_path = tmp_path / ".streamlit" / "secrets.toml"
    streamlit_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text('OPENAI_API_KEY = "local-value"\n', encoding="utf-8")
    streamlit_path.write_text('OPENAI_API_KEY = "streamlit-file-value"\n', encoding="utf-8")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(provider_status, "_streamlit_secrets", lambda: {"OPENAI_API_KEY": "st-secrets-value"})

    value, source = provider_status.resolve_api_key(
        "OPENAI_API_KEY",
        secret_paths=[local_path, streamlit_path],
    )
    assert value == "st-secrets-value"
    assert source == "st.secrets"

    monkeypatch.setattr(provider_status, "_streamlit_secrets", lambda: {})
    value, source = provider_status.resolve_api_key(
        "OPENAI_API_KEY",
        secret_paths=[local_path, streamlit_path],
    )
    assert value == "local-value"
    assert source == "local_file"

    monkeypatch.setenv("OPENAI_API_KEY", "env-value")
    value, source = provider_status.resolve_api_key(
        "OPENAI_API_KEY",
        secret_paths=[local_path, streamlit_path],
    )
    assert value == "env-value"
    assert source == "env"
