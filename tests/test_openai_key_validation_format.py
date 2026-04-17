from app.services import provider_status


def test_openai_key_validation_format():
    assert provider_status.openai_key_format_warning("sk-abc") == ""
    assert provider_status.openai_key_format_warning("sk-proj-abc") == ""

    warning = provider_status.openai_key_format_warning("abc")
    assert "Format inattendu" in warning
