from pathlib import Path

from app.services.provider_status import resolve_api_key


def test_provider_status_sources_openai_google(monkeypatch, tmp_path: Path) -> None:
    local_secrets = tmp_path / "secrets.toml"
    local_secrets.write_text(
        'OPENAI_API_KEY = "local-openai"\nGOOGLE_MAPS_API_KEY = "local-google"\n',
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "env-openai")
    value, source = resolve_api_key("OPENAI_API_KEY", secret_paths=[local_secrets])
    assert value == "env-openai"
    assert source == "env"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.services.provider_status._streamlit_secrets",
        lambda: {"OPENAI_API_KEY": "secrets-openai"},
    )
    value, source = resolve_api_key("OPENAI_API_KEY", secret_paths=[local_secrets])
    assert value == "secrets-openai"
    assert source == "st.secrets"

    monkeypatch.setattr("app.services.provider_status._streamlit_secrets", lambda: {})
    value, source = resolve_api_key("OPENAI_API_KEY", secret_paths=[local_secrets])
    assert value == "local-openai"
    assert source == "local_file"

    value, source = resolve_api_key("GOOGLE_MAPS_API_KEY", secret_paths=[local_secrets])
    assert value == "local-google"
    assert source == "local_file"
