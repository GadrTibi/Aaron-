import os
from pathlib import Path

import pytest

from app.views.settings_keys import write_local_secret


def test_write_local_secret_permissions(tmp_path: Path, monkeypatch) -> None:
    if os.name == "nt":
        pytest.skip("Permissions chmod non applicables sous Windows.")

    monkeypatch.setenv("HOME", str(tmp_path))
    write_local_secret("OPENAI_API_KEY", "secret-value")
    secret_path = tmp_path / ".mfy_local_app" / "secrets.toml"
    assert secret_path.exists()
    mode = secret_path.stat().st_mode & 0o777
    assert mode == 0o600
