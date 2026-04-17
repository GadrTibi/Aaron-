from pathlib import Path

from app.services import provider_status


def test_write_and_delete_local_openai_secret(monkeypatch, tmp_path: Path):
    target = tmp_path / "secrets.toml"
    monkeypatch.setattr(provider_status, "local_secret_path", lambda: target)

    provider_status.write_local_secret("GOOGLE_MAPS_API_KEY", "google-test")
    provider_status.write_local_secret("OPENAI_API_KEY", "sk-test-key")

    content = target.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in content
    assert "GOOGLE_MAPS_API_KEY" in content

    provider_status.delete_local_secret("OPENAI_API_KEY")

    final_content = target.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" not in final_content
    assert "GOOGLE_MAPS_API_KEY" in final_content
